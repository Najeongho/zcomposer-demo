#!/usr/bin/env python
"""
SoftLayer external inventory script.
The SoftLayer Python API client is required. Use `pip install softlayer` to install it.
You have a few different options for configuring your username and api_key. You can pass
environment variables (SL_USERNAME and SL_API_KEY). You can also write INI file to
~/.softlayer or /etc/softlayer.conf. For more information see the SL API at:
- https://softlayer-python.readthedocs.org/en/latest/config_file.html
The SoftLayer Python client has a built in command for saving this configuration file
via the command `sl config setup`.
"""

# Copyright (C) 2014  AJ Bourg <aj@ajbourg.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

#
# I found the structure of the ec2.py script very helpful as an example
# as I put this together. Thanks to whoever wrote that script!
#

import SoftLayer
import requests
import re
import argparse
import itertools
try:
    import json
except:
    import simplejson as json


class SoftLayerInventory(object):

    # Your SoftLayer API username and key.
    softlayer_username = '<Set your IBM Softlayer username>'
    softlayer_api_key = '<Set your IBM Softlayer api key>'

    common_items = [
        'id',
        'globalIdentifier',
        'hostname',
        'domain',
        'fullyQualifiedDomainName',
        'primaryBackendIpAddress',
        'primaryIpAddress',
        'datacenter',
        'tagReferences.tag.name',
        'userData.value',
    ]

    vs_items = [
        'lastKnownPowerState.name',
        'powerState',
        'maxCpu',
        'maxMemory',
        'activeTransaction.transactionStatus[friendlyName,name]',
        'status',
    ]

    def _empty_inventory(self):
        return {"_meta": {"hostvars": {}}}

    def __init__(self):
        '''Main path'''

        self.inventory = self._empty_inventory()

        self.parse_options()

        if self.args.list:
            self.get_all_servers()
            print(self.json_format_dict(self.inventory, True))
        elif self.args.host:
            self.get_virtual_servers()
            print(self.json_format_dict(self.inventory["_meta"]["hostvars"][self.args.host], True))

    def to_safe(self, word):
        '''Converts 'bad' characters in a string to underscores so they can be used as Ansible groups'''

        return re.sub(r"[^A-Za-z0-9\-\.]", "_", word)

    def push(self, my_dict, key, element):
        '''Push an element onto an array that may not have been defined in the dict'''

        if key in my_dict:
            my_dict[key].append(element)
        else:
            my_dict[key] = [element]

    def parse_options(self):
        '''Parse all the arguments from the CLI'''

        parser = argparse.ArgumentParser(description='Produce an Ansible Inventory file based on SoftLayer')
        parser.add_argument('--list', action='store_true', default=False,
                            help='List instances (default: False)')
        parser.add_argument('--host', action='store',
                            help='Get all the variables about a specific instance')
        self.args = parser.parse_args()

    def json_format_dict(self, data, pretty=False):
        '''Converts a dict to a JSON object and dumps it as a formatted string'''

        if pretty:
            return json.dumps(data, sort_keys=True, indent=2)
        else:
            return json.dumps(data)

    def process_instance(self, instance, instance_type="virtual"):
        '''Populate the inventory dictionary with any instance information'''

        # only want active instances
        if 'status' in instance and instance['status']['name'] != 'Active':
            return

        # and powered on instances
        if 'powerState' in instance and instance['powerState']['name'] != 'Running':
            return

        # 5 is active for hardware... see https://forums.softlayer.com/forum/softlayer-developer-network/general-discussion/2955-hardwarestatusid
        if 'hardwareStatusId' in instance and instance['hardwareStatusId'] != 5:
            return

        # if there's no fullyQualifiedDomainName, we can't reach it
        if 'fullyQualifiedDomainName' not in instance:
            return

        instance['userData'] = instance['userData'][0]['value'] if instance['userData'] else ''

        dest = instance['fullyQualifiedDomainName']

        self.inventory["_meta"]["hostvars"][dest] = instance
        self.inventory["_meta"]["hostvars"][dest]['ansible_host'] = self.to_safe(instance['primaryIpAddress'])

        # Inventory: group by datacenter
        self.push(self.inventory, self.to_safe(instance['datacenter']['name']), dest)

        # Inventory: group by domain
        self.push(self.inventory, self.to_safe(instance['domain']), dest)

        # Inventory: group by cpu, memory
        self.push(self.inventory, self.to_safe('c' + str(instance['maxCpu']) + '.m' + str(instance['maxMemory']/1024)), dest)

        # Inventory: group by OS
        serverId = instance['id']
        smask = 'operatingSystem.softwareLicense.softwareDescription'
        virtualGuestDetails = self.client['Virtual_Guest'].getObject(id=serverId, mask=smask)
        self.push(self.inventory, self.to_safe(virtualGuestDetails['operatingSystem']['softwareLicense']['softwareDescription']['referenceCode']), dest)


    def get_virtual_servers(self):
        '''Get all the CCI instances'''
        vs = SoftLayer.VSManager(self.client)
        mask = "mask[%s]" % ','.join(itertools.chain(self.common_items, self.vs_items))
        instances = vs.list_instances(mask=mask)

        for instance in instances:
            self.process_instance(instance)


## Input Softlayer Info

    def get_all_servers(self):  
        self.client = SoftLayer.create_client_from_env(username=self.softlayer_username, api_key=self.softlayer_api_key)
        self.get_virtual_servers()


SoftLayerInventory()