#!/bin/bash

trap continue PIPE

cd -P "$( dirname "${BASH_SOURCE[0]}" )"

read socket_message
while [[ -n "$socket_message" ]]; do
	echo "$socket_message" >>./fake.log

	# handle messages
	if [[ "$socket_message" =~ \{\"msg\":\"[^\"]+\"\} ]];then
		message=$(echo "$socket_message" | sed -r 's/\{\"msg\"\:\"([^\"]+)\"\}/\1/')
		echo "{\"r\":{\"msg\":\"$message\"}}"
	fi

	# handle requests for config
	if [[ "$socket_message" =~ \ *\$\$.* ]];then
		cat ./tinyg-settings.txt
	fi


	read socket_message
done

exit 0