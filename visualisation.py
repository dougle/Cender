import re
import math
import logging
from OpenGL import GL, GLU, GLUT

from PyQt4 import QtCore, QtGui, QtOpenGL


class Visualiser(QtCore.QThread):

    add_command = QtCore.pyqtSignal(str)
    clear = QtCore.pyqtSignal()
    set_config = QtCore.pyqtSignal(str, float)
    tool_position = QtCore.pyqtSignal(str, float)

    def __init__(self, widget=None, parent=None):
        QtCore.QThread.__init__(self, parent)
        self.logger = logging.getLogger(__name__)

        self.widget = widget

        self.add_command.connect(self.add_command_handler)
        self.clear.connect(self.clear_handler)
        self.set_config.connect(self.set_config_handler)
        self.tool_position.connect(self.tool_position_handler)

    def add_command_handler(self, command):
        self.widget.add_tool_path(command)

    def clear_handler(self):
        self.widget.clear_tool_paths()

    def set_config_handler(self, config, value):
        if config == 'chord':
            self.widget.set_chord_length(value)

    def tool_position_handler(self, axis_letter, position):
        self.widget.set_tool_axis_position(axis_letter, position)

    def run(self):
        True


class VisualisationWidget(QtOpenGL.QGLWidget):
    x_rotationChanged = QtCore.pyqtSignal(int)
    y_rotationChanged = QtCore.pyqtSignal(int)
    z_rotationChanged = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super(VisualisationWidget, self).__init__(parent)

        self.logger = logging.getLogger(__name__)

        self.x_key = 'x'
        self.y_key = 'y'
        self.z_key = 'z'
        self.x_offset_key = 'i'
        self.y_offset_key = 'j'
        self.z_offset_key = 'k'

        self.object = None
        self.x_rot = 2880
        self.y_rot = 0
        self.z_rot = 0

        self.x_pos = 0
        self.y_pos = 0
        self.z_pos = 10

        self.tool_x = 0
        self.tool_y = 0
        self.tool_z = 0

        self.last_x_coord = 0
        self.last_y_coord = 0
        self.last_z_coord = 0

        self.chord_length = 0.1

        self.vertices = []

        self.lastPos = QtCore.QPoint()

        self.background = QtGui.QColor.fromCmykF(0, 0, 0, 1)
        self.blank = QtGui.QColor.fromRgbF(0, 0, 0, 1)
        self.rapid = QtGui.QColor.fromCmykF(0, 0.99, 1, 0)
        self.feed = QtGui.QColor.fromCmykF(1, 0, 1, 0.61)
        self.tool = QtGui.QColor.fromCmykF(0.3, 0, 0.99, 0)

        self.quadric = GLU.gluNewQuadric()
        # // Create Smooth Normals
        GLU.gluQuadricNormals(self.quadric, GLU.GLU_SMOOTH)
        GLU.gluQuadricTexture(self.quadric, GL.GL_TRUE)

    def set_chord_length(self, length):
        self.chord_length = float(length)

    def set_x_rotation(self, angle):
        angle = self.normalize_angle(angle)
        if angle != self.x_rot:
            self.x_rot = angle
            self.x_rotationChanged.emit(angle)
            self.updateGL()

    def set_y_rotation(self, angle):
        angle = self.normalize_angle(angle)
        if angle != self.y_rot:
            self.y_rot = angle
            self.y_rotationChanged.emit(angle)
            self.updateGL()

    def set_x_position(self, coord):
        # print "X is "+str(coord)
        self.x_pos = coord
        self.updateGL()

    def set_y_position(self, coord):
        # print "Y is "+str(coord)
        self.y_pos = coord
        self.updateGL()

    def set_z_position(self, coord):
        # print "Z is "+str(coord)
        self.z_pos = max(10, coord)
        self.updateGL()

    def normalize_angle(self, angle):
        while angle < 0:
            angle += 360 * 16
        while angle > 360 * 16:
            angle -= 360 * 16
        return angle

    def render_tool_paths(self):
        GL.glNewList(self.tool_path_list, GL.GL_COMPILE)

        GL.glBegin(GL.GL_LINE_STRIP)

        # draw lines
        for vertex in self.vertices:
            # print vertex
            self.qglColor(vertex['colour'])

            if 'x' in vertex:
                self.last_x_coord = float(vertex['x'])
            if 'y' in vertex:
                self.last_y_coord = float(vertex['y'])
            if 'z' in vertex:
                self.last_z_coord = float(vertex['z'])

            GL.glVertex3f(
                self.last_x_coord * 3,
                self.last_y_coord * 3,
                self.last_z_coord * 3)

        # TODO keep track of extents and zoom to fit

        GL.glEnd()
        GL.glEndList()

    def render_tool(self):
        GL.glNewList(self.tool_list, GL.GL_COMPILE)

        # draw cone
        GL.glPushMatrix()
        self.qglColor(self.tool)
        GL.glTranslatef(self.tool_x, self.tool_y, self.tool_z)
        GLU.gluCylinder(self.quadric, 0, 10, 10, 100, 10)
        GL.glPopMatrix()

        # draw shank
        GL.glPushMatrix()
        self.qglColor(self.tool)
        GL.glTranslatef(self.tool_x, self.tool_y, self.tool_z + 10)
        GLU.gluCylinder(self.quadric, 10, 10, 100, 100, 100)
        GL.glPopMatrix()

        GL.glPushMatrix()
        GL.glTranslatef(self.tool_x, self.tool_y, self.tool_z + 110)
        GLU.gluDisk(self.quadric, 0, 10.1, 100, 10)
        GL.glPopMatrix()

        GL.glEndList()

    def clear_tool_paths(self):
        self.vertices = []
        self.updateGL()

    def set_tool_axis_position(self, axis_letter, position):
        setattr(self, str('tool_' + axis_letter.toLower()), float(position))

    def set_tool_position(self, x=None, y=None, z=None):
        if x is not None:
            self.tool_x = x
        if y is not None:
            self.tool_y = y
        if z is not None:
            self.tool_z = z

        self.updateGL()

    def set_current_position(self, x, y, z):
        self.vertices.append({
            'colour': self.blank,
            'x': x,
            'y': y,
            'z': z})

    def add_tool_path(self, command):
        if len(command) > 0:
            for vertex in self.parse_command(command):
                self.vertices.append(vertex)

            self.updateGL()

    def set_plane(self, command):
        match = re.search(r'^G([\d\.]+)', command)
        if match is not None:
            plane = match.group(1)
            if plane == '17':
                # XY Plane
                self.x_key = 'x'
                self.y_key = 'y'
                self.z_key = 'z'
                self.x_offset_key = 'i'
                self.y_offset_key = 'j'
                self.z_offset_key = 'k'
            if plane == '18':
                # XZ Plane
                self.x_key = 'x'
                self.y_key = 'z'
                self.z_key = 'y'
                self.x_offset_key = 'i'
                self.y_offset_key = 'k'
                self.z_offset_key = 'j'
            if plane == '19':
                # YZ Plane
                self.x_key = 'y'
                self.y_key = 'z'
                self.z_key = 'x'
                self.x_offset_key = 'j'
                self.y_offset_key = 'k'
                self.z_offset_key = 'i'

    def parse_command(self, command):
        # ignore N line numbers when finding command number
        match = re.match(
            r'^(?:N\d+ )?G(\d+)', command.trimmed(), re.IGNORECASE)

        vertices = []

        if match is not None:
            movement_code = int(match.group(1))

            if 0 <= movement_code <= 1:
                vertex = self.parse_line(movement_code, command)
                print vertex
                vertices += vertex
            elif 2 <= movement_code <= 3:
                vertex = self.parse_arc(movement_code, command)
                print vertex
                vertices += vertex
            elif 17 <= movement_code <= 19:
                self.set_plane(match.group(0))

        return vertices

    def parse_line(self, movement_code, command):
        command_codes = {}

        coords = re.findall(
            r'([xyz]) *([\d\.]+)',
            command,
            re.IGNORECASE)

        for coord in coords:
            command_codes[str(coord[0].toLower())] = coord[1]

        colour = self.feed
        if movement_code == 0:
            colour = self.rapid

        vertex = {
            'colour': colour,
            'command': str(command)}

        for dimension in ['x', 'y', 'z']:
            if dimension in command_codes:
                vertex[dimension] = float(command_codes[dimension])

        return [vertex]

    def parse_arc(self, movement_code, command):
        # print command
        # print "lastx %f lasty %f lastz %f" % (self.last_x_coord,
        # self.last_y_coord, self.last_z_coord)

        last_x = getattr(self, 'last_' + self.x_key + '_coord')
        last_y = getattr(self, 'last_' + self.y_key + '_coord')
        last_z = getattr(self, 'last_' + self.z_key + '_coord')
        command_codes = {}

        coords = re.findall(
            r'([xyzijkrp]) *([\-\+]?[\d\.]+)',
            command,
            re.IGNORECASE)

        # fetch all provided coordinates
        for coord in coords:
            command_codes[str(coord[0].toLower())] = float(coord[1])

        # default finish coordinates to current
        for axis in ['x', 'y', 'z']:
            if axis not in command_codes:
                attr_name = ''.join([
                    'last_',
                    getattr(self, axis + '_key'),
                    '_coord'])
                command_codes[axis] = getattr(
                    self, attr_name)

        # default offsets to zero if not provided
        for offset in ['i', 'j', 'k', 'p']:
            if offset not in command_codes:
                command_codes[offset] = 0

        # clockwise or anticlockwise
        direction = -1
        if movement_code == 3:
            direction = 1
        # print "direction %i" % (direction)
        radius = 0

        # calculate the difference between the start and end point
        dx = dy = dz = 0
        if self.x_key in command_codes:
            dx = (command_codes[self.x_key] - last_x)
        if self.y_key in command_codes:
            dy = (command_codes[self.y_key] - last_y)
        if self.z_key in command_codes:
            dz = (command_codes[self.z_key] - last_z)
        # print "dx %f dy %f dz %f" % (dx, dy, dz)

        # calculate the center coords if we have an r value
        if 'r' in command_codes:
            radius = math.fabs(command_codes['r'])

            half_hyp = math.hypot(dx, dy) / 2
            start_to_end_incline = math.atan2(dy, dx)
            # point_to_point_incline = math.acos( (dx/2) / half_mid_hyp )

            # print "start_to_end_incline %f half_hyp %f radius %f" %
            # (start_to_end_incline, half_hyp, radius)

            major_minor = -1
            if command_codes['r'] < 0:
                major_minor = 1

            incline = start_to_end_incline + \
                (math.acos(half_hyp / radius) * major_minor)

            cdx = math.cos(incline) * radius
            cdy = math.sin(incline) * radius

            # print "cdx %f cdy %f" % (cdx, cdy)

            command_codes[self.x_offset_key] = cdx
            command_codes[self.y_offset_key] = cdy
            command_codes[self.z_offset_key] = 0

            del command_codes['r']

        else:
            radius = math.hypot(
                command_codes[self.x_offset_key],
                command_codes[self.y_offset_key])

            # log and abort this command if our params
            # give us a weird radius
            if radius <= 0:
                self.logger.debug(
                    'Computed radius is negative or zero, check command: '
                    + command)
                return []

        # print "x %f y %f z %f i %f j %f k %f" % (command_codes[self.x_key],
        # command_codes[self.y_key],command_codes[self.z_key],command_codes[self.x_offset_key],command_codes[self.y_offset_key],command_codes[self.z_offset_key])

        # check start and end point are equidistant from the center
        # TODO

        center_x = last_x + command_codes[self.x_offset_key]
        center_y = last_y + command_codes[self.y_offset_key]

        # print "center_x %f center_y %f radius %f" % (center_x, center_y,
        # radius)

        # calculate the angle between start and end points
        start_angle = math.atan2(
            (command_codes[self.y_offset_key] * -1),
            (command_codes[self.x_offset_key] * -1))

        end_point_y_offset = (
            command_codes[self.y_key]
            - last_y
            - command_codes[self.y_offset_key])
        end_point_x_offset = (
            command_codes[self.x_key]
            - last_x
            - command_codes[self.x_offset_key])
        end_angle = math.atan2(end_point_y_offset, end_point_x_offset)

        # print "(%f - %f - %f), (%f - %f - %f)" %
        # (command_codes[self.y_key],last_y,command_codes[self.y_offset_key],command_codes[self.x_key],last_x,command_codes[self.x_offset_key])

        # print "start_angle %f end_angle %f" % (start_angle, end_angle)

        max_angle = math.fabs(start_angle - end_angle)

        # add on some full revolutions
        max_angle += ((2 * math.pi) * command_codes['p'])
        # max_angle = (max_angle * direction)

        current_angle = angle_of_each_chord = (
            (self.chord_length / (2 * math.pi * radius)) * (2 * math.pi))
        z_offset_per_chord = (dz * (angle_of_each_chord / max_angle))

        # print "max_angle %f angle_of_each_chord %f z_offset_per_chord %f
        # current_angle %f" % (max_angle, angle_of_each_chord,
        # z_offset_per_chord, current_angle)

        step = 1
        vertices = []
        new_x = last_x
        new_y = last_y
        new_z = last_z
        while current_angle <= max_angle:
            # print "current_angle %f" % current_angle

            comp_angle = (start_angle + (current_angle * direction))

            # print "comparative angle %f" % (comp_angle)

            new_x = center_x + ((math.cos(comp_angle) * radius))
            new_y = center_y + ((math.sin(comp_angle) * radius))
            new_z = (last_z + (z_offset_per_chord * step))

            vertices.append({
                'colour': self.feed,
                'command': command,
                self.x_key: new_x,
                self.y_key: new_y,
                self.z_key: new_z
            })

            # print "new_x %f   new_y %f   new_z %f" % (new_x, new_y, new_z)

            if current_angle == max_angle:
                break

            current_angle += angle_of_each_chord

            if current_angle > max_angle:
                current_angle = max_angle
            step += 1

        setattr(self, 'last_' + self.x_key + '_coord', new_x)
        setattr(self, 'last_' + self.y_key + '_coord', new_y)
        setattr(self, 'last_' + self.z_key + '_coord', new_z)

        return vertices

    # inherited methods
    def minimumSizeHint(self):
        return QtCore.QSize(50, 50)

    def sizeHint(self):
        return QtCore.QSize(400, 400)

    def initializeGL(self):
        self.qglClearColor(self.background)
        GL.glShadeModel(GL.GL_FLAT)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_CULL_FACE)

        self.tool_list = GL.glGenLists(1)
        self.tool_path_list = GL.glGenLists(1)

    def paintGL(self):
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        GL.glLoadIdentity()
        GL.glOrtho(-self.z_pos, self.z_pos, self.z_pos, -self.z_pos,
                   self.z_pos + 999, -self.z_pos - 999)
        GL.glTranslated(self.x_pos, self.y_pos, 0)
        GL.glRotated(self.x_rot / 16.0, 1.0, 0.0, 0.0)
        GL.glRotated(self.y_rot / 16.0, 0.0, 1.0, 0.0)
        GL.glRotated(self.z_rot / 16.0, 0.0, 0.0, 1.0)

        self.render_tool_paths()
        self.render_tool()

        GL.glCallList(self.tool_path_list)
        GL.glCallList(self.tool_list)

    def resizeGL(self, width, height):
        GL.glViewport(0, 0, width, height)

        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GL.glOrtho(-self.z_pos, self.z_pos, -self.z_pos, +self.z_pos,
                   self.z_pos + 999, -self.z_pos - 999)
        GL.glMatrixMode(GL.GL_MODELVIEW)

    # inherited event handlers
    def wheelEvent(self, event):
        self.z_pos += (event.delta() / 10)
        self.set_z_position(self.z_pos)

    def mousePressEvent(self, event):
        self.lastPos = event.pos()

    def mouseMoveEvent(self, event):
        dx = event.x() - self.lastPos.x()
        dy = event.y() - self.lastPos.y()

        if event.buttons() & QtCore.Qt.LeftButton:
            self.set_x_rotation(self.x_rot + 8 * dy)
            self.set_y_rotation(self.y_rot + 8 * dx)

            self.lastPos = event.pos()
        elif event.buttons() & QtCore.Qt.RightButton:
            self.set_x_position(dx)
            self.set_y_position(dy)
