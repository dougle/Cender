import re
import math
import logging
from OpenGL import GL, GLU, GLUT

from PyQt4 import QtCore, QtGui, QtOpenGL


class VisualisationWidget(QtOpenGL.QGLWidget):
    xRotationChanged = QtCore.pyqtSignal(int)
    yRotationChanged = QtCore.pyqtSignal(int)
    zRotationChanged = QtCore.pyqtSignal(int)

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
        self.xRot = 2880
        self.yRot = 0
        self.zRot = 0

        self.xPos = 0
        self.yPos = 0
        self.zPos = 10

        self.tool_x = 0
        self.tool_y = 0
        self.tool_z = 0

        self.lastXCoord = 0
        self.lastYCoord = 0
        self.lastZCoord = 0

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

    def minimumSizeHint(self):
        return QtCore.QSize(50, 50)

    def sizeHint(self):
        return QtCore.QSize(400, 400)

    def setXRotation(self, angle):
        angle = self.normalizeAngle(angle)
        if angle != self.xRot:
            self.xRot = angle
            self.xRotationChanged.emit(angle)
            self.updateGL()

    def setYRotation(self, angle):
        angle = self.normalizeAngle(angle)
        if angle != self.yRot:
            self.yRot = angle
            self.yRotationChanged.emit(angle)
            self.updateGL()

    def setXPosition(self, coord):
        # print "X is "+str(coord)
        self.xPos = coord
        self.updateGL()

    def setYPosition(self, coord):
        # print "Y is "+str(coord)
        self.yPos = coord
        self.updateGL()

    def setZPosition(self, coord):
        # print "Z is "+str(coord)
        self.zPos = max(10, coord)
        self.updateGL()

    # def setZRotation(self, angle):
    #     angle = self.normalizeAngle(angle)
    #     if angle != self.zRot:
    #         self.zRot = angle
    #         self.zRotationChanged.emit(angle)
    #         self.updateGL()

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
        GL.glOrtho(-self.zPos, self.zPos, self.zPos, -self.zPos,
                   self.zPos + 999, -self.zPos - 999)
        GL.glTranslated(self.xPos, self.yPos, 0)
        GL.glRotated(self.xRot / 16.0, 1.0, 0.0, 0.0)
        GL.glRotated(self.yRot / 16.0, 0.0, 1.0, 0.0)
        GL.glRotated(self.zRot / 16.0, 0.0, 0.0, 1.0)

        self.renderToolPaths()
        self.renderTool()

        GL.glCallList(self.tool_path_list)
        GL.glCallList(self.tool_list)

    def resizeGL(self, width, height):
        GL.glViewport(0, 0, width, height)

        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GL.glOrtho(-self.zPos, self.zPos, -self.zPos, +self.zPos,
                   self.zPos + 999, -self.zPos - 999)
        GL.glMatrixMode(GL.GL_MODELVIEW)

    def wheelEvent(self, event):
        self.zPos += (event.delta() / 10)
        self.setZPosition(self.zPos)

    def mousePressEvent(self, event):
        self.lastPos = event.pos()

    def mouseMoveEvent(self, event):
        dx = event.x() - self.lastPos.x()
        dy = event.y() - self.lastPos.y()

        if event.buttons() & QtCore.Qt.LeftButton:
            self.setXRotation(self.xRot + 8 * dy)
            self.setYRotation(self.yRot + 8 * dx)

            self.lastPos = event.pos()
        elif event.buttons() & QtCore.Qt.RightButton:
            self.setXPosition(dx)
            self.setYPosition(dy)

    def normalizeAngle(self, angle):
        while angle < 0:
            angle += 360 * 16
        while angle > 360 * 16:
            angle -= 360 * 16
        return angle

    def renderToolPaths(self):
        GL.glNewList(self.tool_path_list, GL.GL_COMPILE)

        GL.glBegin(GL.GL_LINE_STRIP)

        # draw lines
        for vertex in self.vertices:
            # print vertex
            self.qglColor(vertex['colour'])

            if 'x' in vertex:
                self.lastXCoord = float(vertex['x'])
            if 'y' in vertex:
                self.lastYCoord = float(vertex['y'])
            if 'z' in vertex:
                self.lastZCoord = float(vertex['z'])

            GL.glVertex3f(
                self.lastXCoord * 3,
                self.lastYCoord * 3,
                self.lastZCoord * 3)

        # TODO keep track of extents and zoom to fit

        GL.glEnd()
        GL.glEndList()

    def renderTool(self):
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

    def clearToolPaths(self):
        self.vertices = []
        self.updateGL()

    def setToolAxisPosition(self, axis_letter, position):
        setattr(self, 'tool_' + axis_letter.lower(), position)

    def setToolPosition(self, x=None, y=None, z=None):
        if x is not None:
            self.tool_x = x
        if y is not None:
            self.tool_y = y
        if z is not None:
            self.tool_z = z

        self.updateGL()

    def setCurrentPosition(self, x, y, z):
        self.vertices.append({
            'colour': self.blank,
            'x': x,
            'y': y,
            'z': z})

    def addToolPath(self, command):
        if len(command) > 0:
            for vertex in self.parseCommand(command):
                self.vertices.append(vertex)

            self.updateGL()

    def setPlane(self, command):
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

    def parseCommand(self, command):
        # ignore N line numbers when finding command number
        match = re.match(
            r'^(?:N\d+ )?G(\d+)', str(command).strip(), re.IGNORECASE)

        vertices = []

        if match is not None:
            movement_code = int(match.group(1))

            if 0 <= movement_code <= 1:
                vertices += self.parse_line(movement_code, command)
            elif 2 <= movement_code <= 3:
                vertices += self.parse_arc(movement_code, command)
            elif 17 <= movement_code <= 19:
                self.setPlane(match.group(0))

        return vertices

    def parse_line(self, movement_code, command):
        command_codes = {}

        coords = re.findall(
            r'([xyz]) *([\d\.]+)',
            command,
            re.IGNORECASE)

        for coord in coords:
            command_codes[coord[0].lower()] = coord[1]

        colour = self.feed
        if movement_code == 0:
            colour = self.rapid

        vertex = {
            'colour': colour,
            'command': command}

        for dimension in ['x', 'y', 'z']:
            if dimension in command_codes:
                vertex[dimension] = float(command_codes[dimension])

        return [vertex]

    def parse_arc(self, movement_code, command):
        # print command
        # print "lastx %f lasty %f lastz %f" % (self.lastXCoord,
        # self.lastYCoord, self.lastZCoord)

        last_x = getattr(self, 'last' + self.x_key.upper() + 'Coord')
        last_y = getattr(self, 'last' + self.y_key.upper() + 'Coord')
        last_z = getattr(self, 'last' + self.z_key.upper() + 'Coord')
        command_codes = {}

        coords = re.findall(
            r'([xyzijkrp]) *([\-\+]?[\d\.]+)',
            command,
            re.IGNORECASE)

        # fetch all provided coordinates
        for coord in coords:
            command_codes[coord[0].lower()] = float(coord[1])

        # default finish coordinates to current
        for axis in ['x', 'y', 'z']:
            if axis not in command_codes:
                attr_name = ''.join([
                    'last',
                    getattr(self, axis + '_key').upper(),
                    'Coord'])
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
            (0.1 / (2 * math.pi * radius) * (2 * math.pi)))
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

        setattr(self, 'last' + self.x_key.upper() + 'Coord', new_x)
        setattr(self, 'last' + self.y_key.upper() + 'Coord', new_y)
        setattr(self, 'last' + self.z_key.upper() + 'Coord', new_z)

        return vertices
