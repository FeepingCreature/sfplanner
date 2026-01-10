"""Room-related commands: create room, delink, place blueprint."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from satisfactory_planner.core.models import BUILDING_METADATA, snap_port_to_room_edge
from satisfactory_planner.ui.commands.base import Command, get_scene

if TYPE_CHECKING:
    from satisfactory_planner.core.models import Belt, Document, Room, RoomPlacement, Scene
    from satisfactory_planner.ui.canvas import FactoryCanvas

logger = logging.getLogger(__name__)


def _shallow_copy_room_with_new_ids(room: Room) -> tuple[Room, dict[str, str]]:
    """Shallow copy a Room, regenerating IDs for buildings and belts only.

    This is a SHALLOW copy - nested room placements keep their original room_id,
    so linked rooms inside this room stay linked after delink.

    Returns the new room and a mapping of old_id -> new_id for buildings/belts.
    Belt references are updated to use new building IDs.
    """
    from satisfactory_planner.core.models import Room as RoomModel
    from satisfactory_planner.core.models import generate_id

    # Create ID mapping for buildings
    building_id_map: dict[str, str] = {}
    for old_id in room.buildings:
        building_id_map[old_id] = generate_id()

    # Create ID mapping for belts
    belt_id_map: dict[str, str] = {}
    for old_id in room.belts:
        belt_id_map[old_id] = generate_id()

    # Create new room (not deepcopy - we'll copy contents selectively)
    new_room = RoomModel(
        id=generate_id(),
        name=room.name,
        width=room.width,
        height=room.height,
    )

    # Copy buildings with new IDs
    for old_id, building in room.buildings.items():
        new_building = copy.deepcopy(building)
        new_id = building_id_map[old_id]
        new_building.id = new_id
        new_room.buildings[new_id] = new_building

    # Copy belts with new IDs and updated building references
    for old_id, belt in room.belts.items():
        new_belt = copy.deepcopy(belt)
        new_id = belt_id_map[old_id]
        new_belt.id = new_id
        # Update building references
        if new_belt.source_building_id in building_id_map:
            new_belt.source_building_id = building_id_map[new_belt.source_building_id]
        if new_belt.dest_building_id in building_id_map:
            new_belt.dest_building_id = building_id_map[new_belt.dest_building_id]
        new_room.belts[new_id] = new_belt

    # Nested rooms dict is NOT copied - stays empty
    # Nested room *placements* would be in parent document's room_placements
    # and they reference rooms by ID, so they stay linked automatically

    # Combine all ID mappings
    all_id_map = {**building_id_map, **belt_id_map}

    return new_room, all_id_map


def _generate_crossing_belt_ids(
    crossing_belts: tuple[Belt, ...],
) -> tuple[tuple[str, str, str, str], ...]:
    """Generate IDs for crossing belt ports/belts at construction time."""
    from satisfactory_planner.core.models import generate_id

    return tuple((belt.id, generate_id(), generate_id(), generate_id()) for belt in crossing_belts)


@dataclass(frozen=True)
class CreateRoomCommand(Command):
    """Command to create a room from selected buildings.

    Moves buildings and belts into the new room, creating ports for crossing belts.

    Fully immutable - all IDs are pre-generated at construction time. This means
    execute/undo/redo always produce identical results with the same IDs.

    Callers should use CreateRoomCommand.create() factory method to ensure
    all IDs are generated properly.
    """

    parent_scene_room_id: str | None  # None = root document
    rect: tuple[float, float, float, float]  # x, y, width, height
    building_ids: tuple[str, ...]  # Buildings to move into room
    belt_ids: tuple[str, ...]  # Belts fully inside room
    original_crossing_belts: tuple[Belt, ...]  # Belts crossing boundary (captured at creation)
    canvas: FactoryCanvas

    # Pre-generated IDs - must be provided at construction
    created_room_id: str
    created_placement_id: str

    # Pre-generated IDs for ports/belts created from crossing belts
    # Tuple of (original_belt_id, port_id, internal_belt_id, external_belt_id)
    crossing_belt_port_ids: tuple[tuple[str, str, str, str], ...]

    @staticmethod
    def create(
        parent_scene_room_id: str | None,
        rect: tuple[float, float, float, float],
        building_ids: tuple[str, ...],
        belt_ids: tuple[str, ...],
        original_crossing_belts: tuple[Belt, ...],
        canvas: FactoryCanvas,
    ) -> CreateRoomCommand:
        """Factory method that generates all required IDs."""
        from satisfactory_planner.core.models import generate_id

        return CreateRoomCommand(
            parent_scene_room_id=parent_scene_room_id,
            rect=rect,
            building_ids=building_ids,
            belt_ids=belt_ids,
            original_crossing_belts=original_crossing_belts,
            canvas=canvas,
            created_room_id=generate_id(),
            created_placement_id=generate_id(),
            crossing_belt_port_ids=_generate_crossing_belt_ids(original_crossing_belts),
        )

    def execute(self, document: Document) -> None:
        from satisfactory_planner.core import Room, RoomPlacement

        parent = get_scene(document, self.parent_scene_room_id)
        x, y, w, h = self.rect

        # Create the room
        room = Room(
            id=self.created_room_id,
            name=f"Room {len(document.rooms) + 1}",
            width=w,
            height=h,
        )

        # Move buildings into room (translate to room-relative coords)
        for building_id in self.building_ids:
            building = parent.remove_building(building_id)
            if building:
                building.x -= x
                building.y -= y
                room.add_building(building)
                # Remove from canvas (will be re-added as child of RoomItem)
                self.canvas.remove_building_item(building_id)

        # Move internal belts into room
        for belt_id in self.belt_ids:
            belt = parent.remove_belt(belt_id)
            if belt:
                room.add_belt(belt)
                self.canvas.remove_belt_item(belt_id)

        # Add room to document
        document.rooms[room.id] = room

        # Create placement - must exist before handling crossing belts
        # because external belts reference the placement as a building
        placement = RoomPlacement(
            id=self.created_placement_id,
            room_id=room.id,
            x=x,
            y=y,
            parent_room_id=self.parent_scene_room_id,
        )
        document.room_placements[placement.id] = placement

        # Add room item to canvas - must exist before crossing belts
        # so that belt items can look up the placement
        self.canvas.add_room_item(placement, room)

        # Handle crossing belts (same logic for execute and redo - fully deterministic)
        self._handle_crossing_belts(document, parent, room, x, y)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        parent = get_scene(document, self.parent_scene_room_id)
        x, y, _w, _h = self.rect

        # Get the room
        room = document.rooms.get(self.created_room_id)
        if not room:
            logger.warning(f"CreateRoomCommand.undo: room {self.created_room_id} not found")
            return

        # Remove room item from canvas
        self.canvas.remove_room_item(self.created_placement_id)

        # Move buildings back to parent scene (restore absolute coords)
        for building_id in self.building_ids:
            building = room.remove_building(building_id)
            if building:
                building.x += x
                building.y += y
                parent.add_building(building)
                self.canvas.add_building_item(building)

        # Move belts back to parent scene
        for belt_id in self.belt_ids:
            belt = room.remove_belt(belt_id)
            if belt:
                parent.add_belt(belt)
                self.canvas.add_belt_item(belt)

        # Restore crossing belts and remove created ports
        self._undo_crossing_belts(document, parent, room)

        # Remove room and placement from document
        document.rooms.pop(self.created_room_id, None)
        document.room_placements.pop(self.created_placement_id, None)

        self.canvas.notify_mutation()

    def _handle_crossing_belts(
        self,
        document: Document,
        parent: Scene,
        room: Room,
        room_x: float,
        room_y: float,
    ) -> None:
        """Handle belts that cross the room boundary by creating ports.

        Uses pre-generated IDs from crossing_belt_port_ids - fully deterministic.
        Creates:
        - A port building inside the room (PORT_IN or PORT_OUT) with port_index
        - An internal belt connecting the port to the building inside the room
        - An external belt connecting the outside building to the RoomPlacement

        External belts reference the RoomPlacement's ID as the building_id,
        treating the room as a building with ports.
        """
        from satisfactory_planner.core.models import Belt as BeltModel
        from satisfactory_planner.core.models import Building, BuildingType

        room_w = self.rect[2]

        # Track port indices for each direction
        input_port_index = 0
        output_port_index = 0

        for (
            crossing_belt_id,
            port_id,
            internal_belt_id,
            external_belt_id,
        ) in self.crossing_belt_port_ids:
            belt = parent.belts.get(crossing_belt_id)
            if not belt:
                continue

            # Determine direction: is source inside or outside?
            source_inside = belt.source_building_id in self.building_ids
            dest_inside = belt.dest_building_id in self.building_ids

            if source_inside and not dest_inside:
                # Output: source is inside room, create PORT_OUT
                source_building = room.buildings.get(belt.source_building_id)
                if not source_building:
                    continue

                # Position port on right edge, centered on source building
                port_height = BUILDING_METADATA[BuildingType.PORT_OUT].height
                target_y = source_building.y + source_building.height / 2 - port_height / 2
                port_x, port_y, edge = snap_port_to_room_edge(
                    BuildingType.PORT_OUT, room_w, room.height, room_w, target_y
                )
                # Rotation based on which edge the port is on
                from satisfactory_planner.core.port_geometry import EDGE_ROTATIONS

                port_rotation = EDGE_ROTATIONS.get(edge, 0)
                port = Building(
                    id=port_id,
                    building_type=BuildingType.PORT_OUT,
                    x=port_x,
                    y=port_y,
                    rotation=port_rotation,
                    port_index=output_port_index,
                )
                room.add_building(port)

                # Belt inside room: from source to port
                inside_belt = BeltModel(
                    id=internal_belt_id,
                    tier=belt.tier,
                    source_building_id=belt.source_building_id,
                    source_port_index=belt.source_port_index,
                    dest_building_id=port_id,
                    dest_port_index=0,
                    item_id=belt.item_id,
                )
                room.add_belt(inside_belt)

                # External belt: from RoomPlacement (as building) to original destination
                # The RoomPlacement's output port corresponds to this PORT_OUT's port_index
                external_belt = BeltModel(
                    id=external_belt_id,
                    tier=belt.tier,
                    source_building_id=self.created_placement_id,  # Room as building
                    source_port_index=output_port_index,
                    dest_building_id=belt.dest_building_id,
                    dest_port_index=belt.dest_port_index,
                    item_id=belt.item_id,
                )
                parent.add_belt(external_belt)
                self.canvas.add_belt_item(external_belt)

                output_port_index += 1

            elif dest_inside and not source_inside:
                # Input: dest is inside room, create PORT_IN
                dest_building = room.buildings.get(belt.dest_building_id)
                if not dest_building:
                    continue

                # Position port on left edge, centered on dest building
                port_height = BUILDING_METADATA[BuildingType.PORT_IN].height
                target_y = dest_building.y + dest_building.height / 2 - port_height / 2
                port_x, port_y, edge = snap_port_to_room_edge(
                    BuildingType.PORT_IN, room_w, room.height, 0, target_y
                )
                # Rotation based on which edge the port is on
                from satisfactory_planner.core.port_geometry import EDGE_ROTATIONS

                port_rotation = EDGE_ROTATIONS.get(edge, 0)
                port = Building(
                    id=port_id,
                    building_type=BuildingType.PORT_IN,
                    x=port_x,
                    y=port_y,
                    rotation=port_rotation,
                    port_index=input_port_index,
                )
                room.add_building(port)

                # Belt inside room: from port to destination
                inside_belt = BeltModel(
                    id=internal_belt_id,
                    tier=belt.tier,
                    source_building_id=port_id,
                    source_port_index=0,
                    dest_building_id=belt.dest_building_id,
                    dest_port_index=belt.dest_port_index,
                    item_id=belt.item_id,
                )
                room.add_belt(inside_belt)

                # External belt: from original source to RoomPlacement (as building)
                external_belt = BeltModel(
                    id=external_belt_id,
                    tier=belt.tier,
                    source_building_id=belt.source_building_id,
                    source_port_index=belt.source_port_index,
                    dest_building_id=self.created_placement_id,  # Room as building
                    dest_port_index=input_port_index,
                    item_id=belt.item_id,
                )
                parent.add_belt(external_belt)
                self.canvas.add_belt_item(external_belt)

                input_port_index += 1

            # Remove original crossing belt from parent
            parent.remove_belt(crossing_belt_id)
            self.canvas.remove_belt_item(crossing_belt_id)

    def _undo_crossing_belts(
        self,
        document: Document,
        parent: Scene,
        room: Room,
    ) -> None:
        """Undo crossing belt handling - restore original belts, remove ports."""
        # Remove created ports, internal belts, and external belts
        for (
            _crossing_belt_id,
            port_id,
            internal_belt_id,
            external_belt_id,
        ) in self.crossing_belt_port_ids:
            # Remove internal belt from room
            room.remove_belt(internal_belt_id)
            # Remove port from room
            room.remove_building(port_id)
            # Remove external belt from parent scene
            parent.remove_belt(external_belt_id)
            self.canvas.remove_belt_item(external_belt_id)

        # Restore original belts (captured at command creation time)
        for belt in self.original_crossing_belts:
            parent.add_belt(belt)
            self.canvas.add_belt_item(belt)


@dataclass(frozen=True)
class DeleteRoomPlacementCommand(Command):
    """Command to delete a room placement.

    If this is the last placement for a room, also deletes the room and all
    its contents. Use DissolveRoomCommand to restore contents instead.

    State is captured at construction time by the caller who has document access.
    """

    placement_id: str
    canvas: FactoryCanvas

    # Captured state for undo - must be provided at construction
    placement: RoomPlacement
    room: Room
    is_last_placement: bool
    removed_belts: tuple[Belt, ...]  # External belts connected to room ports

    @staticmethod
    def create(
        placement_id: str,
        canvas: FactoryCanvas,
        document: Document,
    ) -> DeleteRoomPlacementCommand | None:
        """Factory method that captures all required state from document."""
        placement = document.room_placements.get(placement_id)
        if not placement:
            logger.warning(f"DeleteRoomPlacementCommand.create: placement {placement_id} not found")
            return None

        room = document.rooms.get(placement.room_id)
        if not room:
            logger.warning(f"DeleteRoomPlacementCommand.create: room {placement.room_id} not found")
            return None

        # Check if this is the last placement
        placements = document.get_placements_for_room(placement.room_id)
        is_last = len(placements) <= 1

        # Find belts connected to this placement's ports
        parent = get_scene(document, placement.parent_room_id)
        removed_belts: list[Belt] = []
        for belt in parent.belts.values():
            if belt.source_building_id == placement_id or belt.dest_building_id == placement_id:
                removed_belts.append(copy.deepcopy(belt))

        return DeleteRoomPlacementCommand(
            placement_id=placement_id,
            canvas=canvas,
            placement=copy.deepcopy(placement),
            room=copy.deepcopy(room),
            is_last_placement=is_last,
            removed_belts=tuple(removed_belts),
        )

    def execute(self, document: Document) -> None:
        placement = document.room_placements.get(self.placement_id)
        if not placement:
            logger.warning(
                f"DeleteRoomPlacementCommand.execute: placement {self.placement_id} not found"
            )
            return

        # Remove belts connected to this placement's ports
        parent = get_scene(document, placement.parent_room_id)
        for belt in self.removed_belts:
            parent.remove_belt(belt.id)
            self.canvas.remove_belt_item(belt.id)

        # Remove room item from canvas
        self.canvas.remove_room_item(self.placement_id)

        # Remove placement
        document.room_placements.pop(self.placement_id, None)

        if self.is_last_placement:
            # Remove room from document (contents are deleted with it)
            document.rooms.pop(self.room.id, None)

        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        if self.is_last_placement:
            # Re-add the room
            room_copy = copy.deepcopy(self.room)
            document.rooms[room_copy.id] = room_copy

        # Re-add placement
        placement_copy = copy.deepcopy(self.placement)
        document.room_placements[placement_copy.id] = placement_copy

        # Re-add room item
        room = document.rooms.get(placement_copy.room_id)
        if room:
            self.canvas.add_room_item(placement_copy, room)

        # Restore removed belts
        if self.removed_belts:
            parent = get_scene(document, self.placement.parent_room_id)
            for belt in self.removed_belts:
                belt_copy = copy.deepcopy(belt)
                parent.add_belt(belt_copy)
                self.canvas.add_belt_item(belt_copy)

        self.canvas.notify_mutation()


@dataclass(frozen=True)
class DissolveRoomCommand(Command):
    """Command to dissolve a room, restoring its contents to the parent scene.

    Unlike delete, this preserves the buildings and belts by moving them back
    to the parent scene at the room's position.

    Handles crossing belts: finds PORT_IN/PORT_OUT buildings, traces the
    internal belt (inside room) and external belt (in parent), and recreates
    a direct belt connecting the original source to original destination.

    State is captured at construction time by the caller who has document access.
    """

    placement_id: str
    canvas: FactoryCanvas

    # Captured state for undo - must be provided at construction
    placement: RoomPlacement
    room: Room
    # External belts that will be removed (for undo)
    removed_external_belts: tuple[Belt, ...]
    # Pre-generated IDs for direct belts that will be created
    # Tuple of (direct_belt_id, tier, source_building_id, source_port_index,
    #           dest_building_id, dest_port_index, item_id)
    direct_belt_specs: tuple[tuple[str, int, str, int, str, int, str | None], ...]

    @staticmethod
    def create(
        placement_id: str,
        canvas: FactoryCanvas,
        document: Document,
    ) -> DissolveRoomCommand | None:
        """Factory method that captures all required state from document."""
        from satisfactory_planner.core.models import BuildingType, generate_id

        placement = document.room_placements.get(placement_id)
        if not placement:
            logger.warning(f"DissolveRoomCommand.create: placement {placement_id} not found")
            return None

        room = document.rooms.get(placement.room_id)
        if not room:
            logger.warning(f"DissolveRoomCommand.create: room {placement.room_id} not found")
            return None

        parent = get_scene(document, placement.parent_room_id)
        removed_external: list[Belt] = []
        direct_belt_specs: list[tuple[str, int, str, int, str, int, str | None]] = []

        # Get all ports in the room
        ports = room.get_ports()

        for port in ports:
            if port.building_type == BuildingType.PORT_IN:
                external_belt = parent.get_belt_at_port(
                    placement_id, port.port_index or 0, is_output=False
                )
                internal_belt = room.get_belt_at_port(port.id, 0, is_output=True)

                if external_belt and internal_belt:
                    direct_belt_specs.append(
                        (
                            generate_id(),
                            external_belt.tier,
                            external_belt.source_building_id,
                            external_belt.source_port_index,
                            internal_belt.dest_building_id,
                            internal_belt.dest_port_index,
                            external_belt.item_id or internal_belt.item_id,
                        )
                    )

                if external_belt:
                    removed_external.append(copy.deepcopy(external_belt))

            elif port.building_type == BuildingType.PORT_OUT:
                external_belt = parent.get_belt_at_port(
                    placement_id, port.port_index or 0, is_output=True
                )
                internal_belt = room.get_belt_at_port(port.id, 0, is_output=False)

                if external_belt and internal_belt:
                    direct_belt_specs.append(
                        (
                            generate_id(),
                            external_belt.tier,
                            internal_belt.source_building_id,
                            internal_belt.source_port_index,
                            external_belt.dest_building_id,
                            external_belt.dest_port_index,
                            internal_belt.item_id or external_belt.item_id,
                        )
                    )

                if external_belt:
                    removed_external.append(copy.deepcopy(external_belt))

        return DissolveRoomCommand(
            placement_id=placement_id,
            canvas=canvas,
            placement=copy.deepcopy(placement),
            room=copy.deepcopy(room),
            removed_external_belts=tuple(removed_external),
            direct_belt_specs=tuple(direct_belt_specs),
        )

    def execute(self, document: Document) -> None:
        from satisfactory_planner.core.models import Belt as BeltModel
        from satisfactory_planner.core.models import BuildingType

        placement = document.room_placements.get(self.placement_id)
        if not placement:
            logger.warning(f"DissolveRoomCommand.execute: placement {self.placement_id} not found")
            return

        room = document.rooms.get(placement.room_id)
        if not room:
            logger.warning(f"DissolveRoomCommand.execute: room {placement.room_id} not found")
            return

        parent = get_scene(document, placement.parent_room_id)

        # Remove external belts
        for belt in self.removed_external_belts:
            parent.remove_belt(belt.id)
            self.canvas.remove_belt_item(belt.id)

        # Remove room item from canvas
        self.canvas.remove_room_item(self.placement_id)

        # Remove placement
        document.room_placements.pop(self.placement_id, None)

        # Get port IDs for filtering
        ports = room.get_ports()
        port_ids = {p.id for p in ports}

        # Restore non-port buildings to parent scene
        for building in list(room.buildings.values()):
            if building.building_type in (BuildingType.PORT_IN, BuildingType.PORT_OUT):
                continue
            building.x += placement.x
            building.y += placement.y
            parent.add_building(building)
            self.canvas.add_building_item(building)

        # Restore non-port belts
        for belt in list(room.belts.values()):
            if belt.source_building_id in port_ids or belt.dest_building_id in port_ids:
                continue
            parent.add_belt(belt)
            self.canvas.add_belt_item(belt)

        # Create direct belts from pre-generated specs
        for spec in self.direct_belt_specs:
            belt_id, tier, src_id, src_port, dst_id, dst_port, item_id = spec
            direct_belt = BeltModel(
                id=belt_id,
                tier=tier,
                source_building_id=src_id,
                source_port_index=src_port,
                dest_building_id=dst_id,
                dest_port_index=dst_port,
                item_id=item_id,
            )
            parent.add_belt(direct_belt)
            self.canvas.add_belt_item(direct_belt)

        # Remove room from document
        document.rooms.pop(room.id, None)

        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        from satisfactory_planner.core.models import BuildingType

        parent = get_scene(document, self.placement.parent_room_id)

        # Re-add the room first (before removing buildings that reference it)
        room_copy = copy.deepcopy(self.room)
        document.rooms[room_copy.id] = room_copy

        # Remove created direct belts
        for spec in self.direct_belt_specs:
            belt_id = spec[0]
            if belt_id in parent.belts:
                parent.remove_belt(belt_id)
                self.canvas.remove_belt_item(belt_id)

        # Get port IDs to know which buildings/belts to skip
        port_ids = {
            b.id
            for b in self.room.buildings.values()
            if b.building_type in (BuildingType.PORT_IN, BuildingType.PORT_OUT)
        }

        # Remove restored buildings from parent (only non-port ones were restored)
        for building_id, building in self.room.buildings.items():
            if building.building_type in (BuildingType.PORT_IN, BuildingType.PORT_OUT):
                continue
            if building_id in parent.buildings:
                parent.remove_building(building_id)
                self.canvas.remove_building_item(building_id)

        # Remove restored belts from parent (only non-port ones were restored)
        for belt_id, belt in self.room.belts.items():
            if belt.source_building_id in port_ids or belt.dest_building_id in port_ids:
                continue
            if belt_id in parent.belts:
                parent.remove_belt(belt_id)
                self.canvas.remove_belt_item(belt_id)

        # Re-add placement
        placement_copy = copy.deepcopy(self.placement)
        document.room_placements[placement_copy.id] = placement_copy

        # Re-add room item
        room = document.rooms.get(placement_copy.room_id)
        if room:
            self.canvas.add_room_item(placement_copy, room)

        # Restore external belts that were removed
        for belt in self.removed_external_belts:
            belt_copy = copy.deepcopy(belt)
            parent.add_belt(belt_copy)
            self.canvas.add_belt_item(belt_copy)

        self.canvas.notify_mutation()


@dataclass(frozen=True)
class DelinkRoomCommand(Command):
    """Command to delink a room placement from its linked instances.

    Creates a deep copy of the Room with new IDs for all contents,
    and points the placement at the new independent room.

    State is captured at construction time by the caller who has document access.
    """

    placement_id: str  # The placement being delinked
    canvas: FactoryCanvas

    # Captured at construction for undo - must be provided
    old_room_id: str
    # Generated at construction for deterministic redo
    new_room_id: str

    @staticmethod
    def create(
        placement_id: str,
        canvas: FactoryCanvas,
        document: Document,
    ) -> DelinkRoomCommand | None:
        """Factory method that captures all required state from document."""
        from satisfactory_planner.core.models import generate_id

        placement = document.room_placements.get(placement_id)
        if not placement:
            logger.warning(f"DelinkRoomCommand.create: placement {placement_id} not found")
            return None

        return DelinkRoomCommand(
            placement_id=placement_id,
            canvas=canvas,
            old_room_id=placement.room_id,
            new_room_id=generate_id(),
        )

    def execute(self, document: Document) -> None:
        placement = document.room_placements.get(self.placement_id)
        if not placement:
            logger.warning(f"DelinkRoomCommand.execute: placement {self.placement_id} not found")
            return

        old_room = document.rooms.get(placement.room_id)
        if not old_room:
            logger.warning(f"DelinkRoomCommand.execute: room {placement.room_id} not found")
            return

        # Check if this is the only placement - nothing to delink
        placements = document.get_placements_for_room(placement.room_id)
        if len(placements) <= 1:
            logger.info("DelinkRoomCommand.execute: room has only one placement, nothing to delink")
            return

        # Shallow copy the room with new IDs (nested rooms stay linked)
        new_room, _id_map = _shallow_copy_room_with_new_ids(old_room)

        # Override the generated ID with our pre-generated one (for deterministic redo)
        new_room.id = self.new_room_id

        # Windows-style naming: "Copy of X"
        new_room.name = f"Copy of {old_room.name}"

        # Add new room to document
        document.rooms[new_room.id] = new_room

        # Point this placement at the new room
        placement.room_id = new_room.id

        # Refresh the canvas
        self.canvas.remove_room_item(self.placement_id)
        self.canvas.add_room_item(placement, new_room)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        placement = document.room_placements.get(self.placement_id)
        if not placement:
            logger.warning(f"DelinkRoomCommand.undo: placement {self.placement_id} not found")
            return

        if not self.old_room_id:
            logger.warning("DelinkRoomCommand.undo: old_room_id not captured")
            return

        old_room = document.rooms.get(self.old_room_id)
        if not old_room:
            logger.warning(f"DelinkRoomCommand.undo: old room {self.old_room_id} not found")
            return

        # Remove the copied room
        document.rooms.pop(self.new_room_id, None)

        # Point placement back at original room
        placement.room_id = self.old_room_id

        # Refresh the canvas
        self.canvas.remove_room_item(self.placement_id)
        self.canvas.add_room_item(placement, old_room)
        self.canvas.notify_mutation()


@dataclass(frozen=True)
class PlaceBlueprintCommand(Command):
    """Command to place a blueprint (room from library) on the canvas.

    If the room ID already exists in the document, creates a linked placement.
    If it doesn't exist, adds the room and creates a placement.
    This allows blueprints to maintain linkage with existing rooms.

    State is captured at construction time by the caller who has document access.
    """

    source_room: Room  # The blueprint room (preserves original ID)
    x: float
    y: float
    canvas: FactoryCanvas

    # Pre-generated placement ID for deterministic undo/redo - must be provided
    created_placement_id: str
    # Track whether we will add the room (determined at construction)
    room_will_be_added: bool

    @staticmethod
    def create(
        source_room: Room,
        x: float,
        y: float,
        canvas: FactoryCanvas,
        document: Document,
    ) -> PlaceBlueprintCommand:
        """Factory method that captures all required state from document."""
        from satisfactory_planner.core.models import generate_id

        # Check if room already exists in document (linked case)
        room_exists = source_room.id in document.rooms

        return PlaceBlueprintCommand(
            source_room=source_room,
            x=x,
            y=y,
            canvas=canvas,
            created_placement_id=generate_id(),
            room_will_be_added=not room_exists,
        )

    def execute(self, document: Document) -> None:
        from satisfactory_planner.core.models import RoomPlacement

        if self.room_will_be_added:
            # Add the room to document (preserving its ID)
            document.rooms[self.source_room.id] = self.source_room

        # Get the room (either existing or just added)
        room = document.rooms[self.source_room.id]

        # Create placement
        placement = RoomPlacement(
            id=self.created_placement_id,
            room_id=room.id,
            x=self.x,
            y=self.y,
            parent_room_id=None,  # Blueprint placement always at root for now
        )
        document.room_placements[placement.id] = placement

        # Add to canvas
        self.canvas.add_room_item(placement, room)
        self.canvas.notify_mutation()

    def undo(self, document: Document) -> None:
        # Remove room item from canvas
        self.canvas.remove_room_item(self.created_placement_id)

        # Remove placement from document
        document.room_placements.pop(self.created_placement_id, None)

        # Only remove room if we added it
        if self.room_will_be_added:
            document.rooms.pop(self.source_room.id, None)

        self.canvas.notify_mutation()
