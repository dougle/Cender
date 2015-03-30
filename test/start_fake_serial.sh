#!/bin/bash


cd -P "$( dirname "${BASH_SOURCE[0]}" )"



usage()
{
cat << EOF
usage: $0 options

This script starts a fake USB device.

OPTIONS:
   -h      Show this message
   -d      Destination device path
EOF
}


DEVICE="/dev/ttyUSB0"

while getopts “hd:” OPTION
do
     case $OPTION in
         h)
             usage
             exit 1
             ;;
         d)
             DEVICE=$OPTARG
             ;;
         ?)
             usage
             exit
             ;;
     esac
done


# must be run as privilaged user
if [[ "$(whoami)" != 'root' ]];then
	echo "Please run this as root"
	exit 1
fi



# start a fake serial device
socat -t 999999999999 -d -d PTY,link=$DEVICE,raw,nonblock,echo=0,crnl,mode=0777 SYSTEM:"bash ./fake_tinyg97_listener.sh"

exit 0