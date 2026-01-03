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
            # Draw as diamond
            size = SPLITTER_SIZE
            x, y = node.x - size / 2, node.y - size / 2
            
            path = QPainterPath()
            path.moveTo(x + size / 2, y)
            path.lineTo(x + size, y + size / 2)
            path.lineTo(x + size / 2, y + size)
            path.lineTo(x, y + size / 2)
            path.closeSubpath()
            
            item = self.scene.addPath(
                path,
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
        
        # Get connection points
        src_x, src_y = self._get_output_point(src)
        tgt_x, tgt_y = self._get_input_point(tgt)
        
        # Draw curved path
        path = QPainterPath()
        path.moveTo(src_x, src_y)
        
        src_is_waypoint = src.node_type == NodeType.WAYPOINT
        tgt_is_waypoint = tgt.node_type == NodeType.WAYPOINT
        
        # All connections use cubic bezier - smooth S-curves
        mid_x = (src_x + tgt_x) / 2
        path.cubicTo(
            mid_x, src_y,
            mid_x, tgt_y,
            tgt_x, tgt_y
        )
        
        # Color based on belt tier
        color = self._belt_color(edge.rate)
        
        item = self.scene.addPath(path, QPen(color, 2))
        
        # Add arrowhead (skip for waypoint targets - too cluttered)
        if not tgt_is_waypoint:
            self._draw_arrowhead(tgt_x, tgt_y, src_x, src_y, color)
        
        # Add label with item name and throughput (skip for waypoint connections)
        if not src_is_waypoint and not tgt_is_waypoint:
            self._draw_edge_label(edge, src_x, src_y, tgt_x, tgt_y)
    
    def _get_output_point(self, node: NetworkNode) -> tuple[float, float]:
        """Get the output connection point for a node."""
        if node.node_type == NodeType.WAYPOINT:
            return node.x, node.y  # Center point
        if node.node_type in (NodeType.SPLITTER, NodeType.MERGER):
            return node.x + SPLITTER_SIZE / 2, node.y
        return node.x + NODE_WIDTH / 2, node.y
    
    def _get_input_point(self, node: NetworkNode) -> tuple[float, float]:
        """Get the input connection point for a node."""
        if node.node_type == NodeType.WAYPOINT:
            return node.x, node.y  # Center point
        if node.node_type in (NodeType.SPLITTER, NodeType.MERGER):
            return node.x - SPLITTER_SIZE / 2, node.y
        return node.x - NODE_WIDTH / 2, node.y
    
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
