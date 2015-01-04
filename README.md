Cender
======

A Gcode sender for TinyG motion controller boards.

Cender will let you:
* Modify and backup your board configuration.
* Jog your machine around and display current coordinates for XYZ and A.
* Specify coordinates absolutely, relatively, as a percentage or arithmetically using the current position.
* Home all axis or individual axis.
* Enter manual Gcode or board specific commands.
* Let you define offsets and change the current position based on those offsets.
* Toggle coolant and spindle including direction and speed.
* Upload and track file progress.
* Monitor board command queue and current velocity.
* Keep updated with your controller's firmware.
* Currently only supports TinyG 0.96 and 0.97 but Cender is structured to accept drivers for all boards past and present.


Installing
------------
Written and tested on python 2.6 and requires pubsub and pyserial.
Uses pyqt for the interface.

Install dependancies
	aptitude install python-qt4
	pip install pubsub pyserial

Download the zip on the right and run (doesn't need root):
	python main.py


Drivers
---------
The structure of cender is a main window object that instantiates a driver based on the user's configuration and chosen board manufacturer and version.

Currently only TinyG versions 0.96 and 0.97 (master and edge) are supported, but new drivers can easily be written to support many many different controller boards.

Drivers for each version normally extend a base class for the manufacturer which contains common code for that range of boards. All drivers extend a base controller class that contains the basic command sending and status receiving thread code.

If you have a spare controller board other than a tinyg and are willing to lend it, short term to me to develop and test a driver please contact me, that would be hugely appreciated.


Known Issues
------------
* For arc gcode G02 and G03, these commands are split into many "chords" before they reach the command queue, they will throw the file progress bar off.
* Grbl stub file is in place but contains no methods, if someone has a Grbl board and can flesh that driver out that would be much appreciated. Alternatively contacting me and lending me a spare grbl shield would also be appreciated hugely.


Contributing
------------
All comments and bug reports are welcome, this code will be kept up-to-date, fixed and improved with new features as and when i stumble across them. Forks and pull requests are also welcome.

Cender has been written to conform to PEP008 and the pep8 utility should be run on all modified files before commiting.