"""Production graph visualization widget."""

import math
from typing import Optional
from PyQt6.QtWidgets import QWidget, QGraphicsView, QGraphicsScene, QGraphicsItem
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QPainterPath, QFont
from PyQt6.QtCore import Qt, QRectF, QPointF

from ..models.network import NetworkGraph, NetworkNode, NetworkEdge, NodeType


# Visual constants
NODE_WIDTH = 120
NODE_HEIGHT = 50
SPLITTER_SIZE = 30
PORT_RADIUS = 5

# Colors by node type
NODE_COLORS = {
    NodeType.RECIPE: QColor(100, 150, 200),
    NodeType.SPLITTER: QColor(200, 200, 100),
    NodeType.MERGER: QColor(200, 150, 100),
    NodeType.SOURCE: QColor(100, 200, 100),
    NodeType.SINK: QColor(200, 100, 100),
    NodeType.WAYPOINT: QColor(80, 80, 80),  # Subtle - just routing helpers
}

EDGE_COLOR = QColor(80, 80, 80)
EDGE_HIGHLIGHT_COLOR = QColor(50, 150, 250)


class ProductionView(QGraphicsView):
    """Widget for displaying and interacting with the production graph."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        # Enable antialiasing
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        # Enable dragging and zooming
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        
        # Current network
        self.network: Optional[NetworkGraph] = None
        
        # Style
        self.setStyleSheet("background-color: #2b2b2b;")
    
    def wheelEvent(self, event):
        """Zoom with mouse wheel."""
        factor = 1.2
        if event.angleDelta().y() < 0:
            factor = 1 / factor
        self.scale(factor, factor)
    
    def set_network(self, network: NetworkGraph):
        """Display a network graph."""
        self.network = network
        self._rebuild_scene()
    
    def clear(self):
        """Clear the display."""
        self.network = None
        self.scene.clear()
    
    def _rebuild_scene(self):
        """Rebuild the scene from the current network."""
        self.scene.clear()
        
        if not self.network:
            return
        
        # Draw edges first (below nodes)
        for edge in self.network.edges:
            self._draw_edge(edge)
        
        # Draw nodes
        for node in self.network.nodes.values():
            self._draw_node(node)
        
        # Fit view to content
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50))
    
    def _draw_node(self, node: NetworkNode):
        """Draw a node on the scene."""
        color = NODE_COLORS.get(node.node_type, QColor(150, 150, 150))
        
        # Waypoints are invisible routing helpers - just draw a tiny dot for debugging
        if node.node_type == NodeType.WAYPOINT:
            size = 6
            self.scene.addEllipse(
                node.x - size / 2, node.y - size / 2, size, size,
                QPen(color), QBrush(color)
            )
            return
        
        if node.node_type in (NodeType.SPLITTER, NodeType.MERGER):
            # Draw as square (like in-game)
            size = SPLITTER_SIZE
            x, y = node.x - size / 2, node.y - size / 2
            
            item = self.scene.addRect(
                x, y, size, size,
                QPen(color.darker(120), 2),
                QBrush(color)
            )
        else:
            # Draw as rounded rectangle
            width = NODE_WIDTH
            height = NODE_HEIGHT
            x, y = node.x - width / 2, node.y - height / 2
            
            item = self.scene.addRect(
                x, y, width, height,
                QPen(color.darker(120), 2),
                QBrush(color)
            )
            
            # Add label
            label = node.label or node.id
            text = self.scene.addText(label)
            text.setDefaultTextColor(Qt.GlobalColor.white)
            text.setFont(QFont("Arial", 9))
            
            # Center text in node
            text_rect = text.boundingRect()
            text.setPos(
                x + (width - text_rect.width()) / 2,
                y + (height - text_rect.height()) / 2
            )
    
    def _draw_edge(self, edge: NetworkEdge):
        """Draw an edge on the scene."""
        src = self.network.get_node(edge.source_id)
        tgt = self.network.get_node(edge.target_id)
        
        if not src or not tgt:
            return
        
        # Get connection points (pass target/source for splitter/merger port selection)
        src_x, src_y = self._get_output_point(src, tgt)
        tgt_x, tgt_y = self._get_input_point(tgt, src)
        
        # Draw curved path
        path = QPainterPath()
        path.moveTo(src_x, src_y)
        
        src_is_waypoint = src.node_type == NodeType.WAYPOINT
        tgt_is_waypoint = tgt.node_type == NodeType.WAYPOINT
        
        # Calculate control points based on tangent directions
        # For waypoints, use direction through the waypoint (predecessor -> successor)
        # For buildings, use horizontal tangent
        
        src_tangent = self._get_outgoing_tangent(src, tgt)
        tgt_tangent = self._get_incoming_tangent(tgt, src)
        
        # Control points: offset along tangent direction
        dist = math.sqrt((tgt_x - src_x) ** 2 + (tgt_y - src_y) ** 2)
        ctrl_dist = dist * 0.4  # Control point distance
        
        ctrl1_x = src_x + src_tangent[0] * ctrl_dist
        ctrl1_y = src_y + src_tangent[1] * ctrl_dist
        ctrl2_x = tgt_x - tgt_tangent[0] * ctrl_dist
        ctrl2_y = tgt_y - tgt_tangent[1] * ctrl_dist
        
        path.cubicTo(ctrl1_x, ctrl1_y, ctrl2_x, ctrl2_y, tgt_x, tgt_y)
        
        # Color based on belt tier
        color = self._belt_color(edge.rate)
        
        item = self.scene.addPath(path, QPen(color, 2))
        
        # Add arrowhead (skip for waypoint targets - too cluttered)
        if not tgt_is_waypoint:
            self._draw_arrowhead(tgt_x, tgt_y, src_x, src_y, color)
        
        # Add label with item name and throughput (skip for waypoint connections)
        if not src_is_waypoint and not tgt_is_waypoint:
            self._draw_edge_label(edge, src_x, src_y, tgt_x, tgt_y)
    
    def _get_output_point(self, node: NetworkNode, target: NetworkNode = None) -> tuple[float, float]:
        """Get the output connection point for a node."""
        if node.node_type == NodeType.WAYPOINT:
            return node.x, node.y  # Center point
        if node.node_type == NodeType.SPLITTER and target:
            # Splitter has 3 outputs: top, middle, right-side bottom
            # Sort outgoing edges by target y position
            port = self._get_splitter_output_port(node, target)
            return self._get_splitter_port_position(node, port, is_output=True)
        if node.node_type in (NodeType.SPLITTER, NodeType.MERGER):
            return node.x + SPLITTER_SIZE / 2, node.y
        return node.x + NODE_WIDTH / 2, node.y
    
    def _get_input_point(self, node: NetworkNode, source: NetworkNode = None) -> tuple[float, float]:
        """Get the input connection point for a node."""
        if node.node_type == NodeType.WAYPOINT:
            return node.x, node.y  # Center point
        if node.node_type == NodeType.MERGER and source:
            # Merger has 3 inputs: top, middle, left-side bottom
            port = self._get_merger_input_port(node, source)
            return self._get_merger_port_position(node, port, is_input=True)
        if node.node_type in (NodeType.SPLITTER, NodeType.MERGER):
            return node.x - SPLITTER_SIZE / 2, node.y
        return node.x - NODE_WIDTH / 2, node.y
    
    def _get_splitter_output_port(self, splitter: NetworkNode, target: NetworkNode) -> int:
        """Get which port (0=top, 1=middle, 2=bottom) for this target."""
        # Get all outgoing edges and sort by target y position
        edges = self.network.edges_from(splitter.id)
        targets_with_y = []
        for e in edges:
            t = self.network.get_node(e.target_id)
            if t:
                targets_with_y.append((e.target_id, t.y))
        targets_with_y.sort(key=lambda x: x[1])  # Sort by y (top to bottom)
        
        # Find which port this target gets
        for i, (tid, _) in enumerate(targets_with_y):
            if tid == target.id:
                return min(i, 2)  # Clamp to 0, 1, 2
        return 1  # Default to middle
    
    def _get_merger_input_port(self, merger: NetworkNode, source: NetworkNode) -> int:
        """Get which port (0=top, 1=middle, 2=bottom) for this source."""
        # Get all incoming edges and sort by source y position
        edges = self.network.edges_to(merger.id)
        sources_with_y = []
        for e in edges:
            s = self.network.get_node(e.source_id)
            if s:
                sources_with_y.append((e.source_id, s.y))
        sources_with_y.sort(key=lambda x: x[1])  # Sort by y (top to bottom)
        
        # Find which port this source gets
        for i, (sid, _) in enumerate(sources_with_y):
            if sid == source.id:
                return min(i, 2)  # Clamp to 0, 1, 2
        return 1  # Default to middle
    
    def _get_splitter_port_position(self, node: NetworkNode, port: int, is_output: bool) -> tuple[float, float]:
        """Get position of a splitter port. Outputs: top-right, right, bottom-right."""
        half = SPLITTER_SIZE / 2
        if port == 0:  # Top
            return node.x + half * 0.5, node.y - half
        elif port == 1:  # Middle (right side)
            return node.x + half, node.y
        else:  # Bottom
            return node.x + half * 0.5, node.y + half
    
    def _get_merger_port_position(self, node: NetworkNode, port: int, is_input: bool) -> tuple[float, float]:
        """Get position of a merger port. Inputs: top-left, left, bottom-left."""
        half = SPLITTER_SIZE / 2
        if port == 0:  # Top
            return node.x - half * 0.5, node.y - half
        elif port == 1:  # Middle (left side)
            return node.x - half, node.y
        else:  # Bottom
            return node.x - half * 0.5, node.y + half
    
    def _get_outgoing_tangent(self, node: NetworkNode, next_node: NetworkNode) -> tuple[float, float]:
        """Get the outgoing tangent direction for a node (normalized)."""
        if node.node_type == NodeType.WAYPOINT:
            # For waypoints, use direction from predecessor through to next node
            preds = self.network.predecessors(node.id)
            if preds:
                pred = self.network.get_node(preds[0])
                if pred:
                    dx = next_node.x - pred.x
                    dy = next_node.y - pred.y
                    length = math.sqrt(dx * dx + dy * dy)
                    if length > 0:
                        return (dx / length, dy / length)
        
        if node.node_type == NodeType.SPLITTER:
            # Splitter outputs: top goes up, middle goes right, bottom goes down
            port = self._get_splitter_output_port(node, next_node)
            if port == 0:  # Top
                return (0.3, -0.95)  # Mostly up, slight right
            elif port == 2:  # Bottom
                return (0.3, 0.95)  # Mostly down, slight right
            else:  # Middle
                return (1.0, 0.0)  # Horizontal right
        
        # For other buildings: blend horizontal with direction (30% influence)
        dx = next_node.x - node.x
        dy = next_node.y - node.y
        length = math.sqrt(dx * dx + dy * dy)
        if length > 0:
            blend = 0.3
            tx = 1.0 * (1 - blend) + (dx / length) * blend
            ty = 0.0 * (1 - blend) + (dy / length) * blend
            tlen = math.sqrt(tx * tx + ty * ty)
            return (tx / tlen, ty / tlen)
        return (1.0, 0.0)
    
    def _get_incoming_tangent(self, node: NetworkNode, prev_node: NetworkNode) -> tuple[float, float]:
        """Get the incoming tangent direction for a node (normalized)."""
        if node.node_type == NodeType.WAYPOINT:
            # For waypoints, use direction from prev_node through to successor
            succs = self.network.successors(node.id)
            if succs:
                succ = self.network.get_node(succs[0])
                if succ:
                    dx = succ.x - prev_node.x
                    dy = succ.y - prev_node.y
                    length = math.sqrt(dx * dx + dy * dy)
                    if length > 0:
                        return (dx / length, dy / length)
        
        if node.node_type == NodeType.MERGER:
            # Merger inputs: top comes from up, middle from left, bottom from down
            port = self._get_merger_input_port(node, prev_node)
            if port == 0:  # Top
                return (0.3, -0.95)  # Mostly up, slight right
            elif port == 2:  # Bottom
                return (0.3, 0.95)  # Mostly down, slight right
            else:  # Middle
                return (1.0, 0.0)  # Horizontal right
        
        # For other buildings: blend horizontal with direction (30% influence)
        dx = node.x - prev_node.x
        dy = node.y - prev_node.y
        length = math.sqrt(dx * dx + dy * dy)
        if length > 0:
            blend = 0.3
            tx = 1.0 * (1 - blend) + (dx / length) * blend
            ty = 0.0 * (1 - blend) + (dy / length) * blend
            tlen = math.sqrt(tx * tx + ty * ty)
            return (tx / tlen, ty / tlen)
        return (1.0, 0.0)
    
    def _belt_color(self, rate: float) -> QColor:
        """Get color for a belt based on its rate."""
        # Gradient from green (low) to red (high)
        max_rate = 360  # Tier 6
        ratio = min(rate / max_rate, 1.0)
        
        r = int(80 + ratio * 120)
        g = int(200 - ratio * 120)
        b = 80
        
        return QColor(r, g, b)
    
    def _draw_edge_label(self, edge: NetworkEdge, src_x: float, src_y: float, tgt_x: float, tgt_y: float):
        """Draw a label on an edge showing item and throughput."""
        # Position at midpoint
        mid_x = (src_x + tgt_x) / 2
        mid_y = (src_y + tgt_y) / 2
        
        # Format label: "Item (rate/min)"
        label_text = f"{edge.item}\n{edge.rate:.1f}/min"
        
        text = self.scene.addText(label_text)
        text.setDefaultTextColor(QColor(220, 220, 220))
        text.setFont(QFont("Arial", 7))
        
        # Center text on midpoint, offset slightly above the line
        text_rect = text.boundingRect()
        text.setPos(
            mid_x - text_rect.width() / 2,
            mid_y - text_rect.height() - 2
        )
        
        # Add subtle background for readability
        bg_rect = self.scene.addRect(
            mid_x - text_rect.width() / 2 - 2,
            mid_y - text_rect.height() - 4,
            text_rect.width() + 4,
            text_rect.height() + 2,
            QPen(Qt.PenStyle.NoPen),
            QBrush(QColor(40, 40, 40, 180))
        )
        bg_rect.setZValue(-1)  # Behind text
    
    def _draw_arrowhead(self, x: float, y: float, from_x: float, from_y: float, color: QColor):
        """Draw an arrowhead at the target point."""
        angle = math.atan2(y - from_y, x - from_x)
        arrow_size = 8
        
        path = QPainterPath()
        path.moveTo(x, y)
        path.lineTo(
            x - arrow_size * math.cos(angle - math.pi / 6),
            y - arrow_size * math.sin(angle - math.pi / 6)
        )
        path.lineTo(
            x - arrow_size * math.cos(angle + math.pi / 6),
            y - arrow_size * math.sin(angle + math.pi / 6)
        )
        path.closeSubpath()
        
        self.scene.addPath(path, QPen(color), QBrush(color))
    
    def fit_to_content(self):
        """Fit the view to show all content."""
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
