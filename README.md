# NETWATCH

**NETWATCH** is tool to monitor servers' and services' availability.

it supports following parameters:

- -d | --daemon | --start     => start the tool as daemon
- -s | --stop                 => stop the tool daemon
- -p | --status               => prints out the current PID

otherwise it will only run once. Please also check the following config params:

- **hosts**
- - This parameter is a dictionary:
- - name: name for the server/machine
- - address: ip address or hostname for the machine
- - ports: ports/services to test. can be set to None or a list of ports
- **check_interval**
- - check interval in seconds for hosts and services
- **email_interval**
- - email interval in seconds for email notifications
