#!/usr/bin/env python
# -*- coding: utf-8 -*-

###############################################################################
#  Copyright 2015 Kitware Inc.
#
#  Licensed under the Apache License, Version 2.0 ( the "License" );
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

from tests import base
import json
import mock
from cumulus.testing import AssertCallsMixin
import unittest

def setUpModule():
    base.enabledPlugins.append('cumulus')
    base.startServer()


def tearDownModule():
    base.stopServer()


class VolumeTestCase(AssertCallsMixin, base.TestCase):

    @mock.patch('cumulus.aws.ec2.tasks.key.generate_key_pair.delay')
    @mock.patch('cumulus.ssh.tasks.key.generate_key_pair.delay')
    @mock.patch('girder.plugins.cumulus.models.aws.get_ec2_client')
    def setUp(self, get_ec2_client, *args):
        super(VolumeTestCase, self).setUp()

        users = ({
            'email': 'cumulus@email.com',
            'login': 'cumulus',
            'firstName': 'First',
            'lastName': 'Last',
            'password': 'goodpassword'
        }, {
            'email': 'regularuser@email.com',
            'login': 'regularuser',
            'firstName': 'First',
            'lastName': 'Last',
            'password': 'goodpassword'
        }, {
            'email': 'another@email.com',
            'login': 'another',
            'firstName': 'First',
            'lastName': 'Last',
            'password': 'goodpassword'
        })
        self._cumulus, self._user, self._another_user = \
            [self.model('user').createUser(**user) for user in users]

        self._group = self.model('group').createGroup('cumulus', self._cumulus)

        # Create a traditional cluster
        body = {
            'config': {
                'host': 'myhost',
                'ssh': {
                    'user': 'myuser'
                }
            },
            'name': 'test',
            'type': 'trad'
        }

        json_body = json.dumps(body)

        r = self.request('/clusters', method='POST',
                         type='application/json', body=json_body, user=self._user)
        self.assertStatus(r, 201)
        self._trad_cluster_id = str(r.json['_id'])

        # Create a AWS profile
        self._availability_zone = 'cornwall-2b'
        body = {
            'name': 'myprof',
            'accessKeyId': 'mykeyId',
            'secretAccessKey': 'mysecret',
            'regionName': 'cornwall',
            'availabilityZone': self._availability_zone
        }

        ec2_client = get_ec2_client.return_value
        ec2_client.describe_regions.return_value = {
            'Regions': [{
                'RegionName': 'cornwall',
                'Endpoint': 'cornwall.ec2.amazon.com'
                }]
        }

        create_url = '/user/%s/aws/profiles' % str(self._user['_id'])
        r = self.request(create_url, method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatus(r, 201)
        self._profile_id = str(r.json['_id'])

        create_url = '/user/%s/aws/profiles' % str(self._another_user['_id'])
        r = self.request(create_url, method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._another_user)
        self.assertStatus(r, 201)
        self._another_profile_id = str(r.json['_id'])

        # Create EC2 cluster
        body = {
            'profileId': self._profile_id,
            'name': 'testing'
        }

        json_body = json.dumps(body)

        r = self.request('/clusters', method='POST',
                         type='application/json', body=json_body, user=self._user)
        self.assertStatus(r, 201)
        self._cluster_id = str(r.json['_id'])

    @unittest.skip('Skipping until https://github.com/Kitware/cumulus/issues/242 is fixed')
    @mock.patch('girder.plugins.cumulus.models.aws.get_ec2_client')
    def test_create(self, get_ec2_client):
        volume_id = 'vol-1'
        ec2_client = get_ec2_client.return_value
        ec2_client.create_volume.return_value = {
            'VolumeId': volume_id
        }

        body = {
            'name': 'test',
            'size': 20,
            'zone': 'us-west-2a',
            'type': 'ebs',
            'profileId': self._profile_id
        }

        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatus(r, 201)
        expected = {
            u'name': u'test',
            u'zone': u'us-west-2a',
            u'type': u'ebs',
            u'size': 20,
            u'ec2': {
                u'id': volume_id
            },
            u'profileId': self._profile_id
        }
        del r.json['_id']
        self.assertEqual(r.json, expected, 'Unexpected volume returned')

        # Try invalid type
        body['type'] = 'bogus'
        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._cumulus)
        self.assertStatus(r, 400)
        # Add file system type
        body = {
            'name': 'test2',
            'size': 20,
            'zone': 'us-west-2a',
            'type': 'ebs',
            'fs': 'ext4',
            'profileId': self._profile_id
        }
        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._cumulus)
        self.assertStatus(r, 201)
        expected = {
            u'name': u'test2',
            u'zone': u'us-west-2a',
            u'type': u'ebs',
            u'size': 20,
            u'fs': u'ext4',
            u'ec2': {
                u'id': volume_id
            },
            u'profileId': self._profile_id
        }
        del r.json['_id']

        self.assertEqual(r.json, expected, 'Unexpected volume returned')
        # Try invalid file system type
        body['fs'] = 'bogus'
        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._cumulus)
        self.assertStatus(r, 400)

        # Try create volume with same name
        body = {
            'name': 'test',
            'size': 20,
            'zone': 'us-west-2a',
            'type': 'ebs',
            'profileId': self._profile_id
        }

        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatus(r, 400)

        # Now try create volume with same name another user this should work
        body = {
            'name': 'test',
            'size': 20,
            'zone': 'us-west-2a',
            'type': 'ebs',
            'profileId': self._profile_id
        }

        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._cumulus)
        self.assertStatus(r, 201)

        # Create a volume without a zone
        body = {
            'name': 'zoneless',
            'size': 20,
            'type': 'ebs',
            'profileId': self._profile_id
        }

        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._cumulus)
        self.assertStatus(r, 201)
        self.assertEqual(r.json['zone'], self._availability_zone,
                         'Volume created in wrong zone')

        # Try to create a volume with a invalid profile
        body['aws'] = {
            'profileId': 'bogus'
        }
        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._cumulus)
        self.assertStatus(r, 400)

    @unittest.skip('Skipping until https://github.com/Kitware/cumulus/issues/242 is fixed')
    @mock.patch('girder.plugins.cumulus.models.aws.get_ec2_client')
    def test_get(self, get_ec2_client):
        volume_id = 'vol-1'
        ec2_client = get_ec2_client.return_value
        ec2_client.create_volume.return_value = {
            'VolumeId': volume_id
        }

        body = {
            'name': 'test',
            'size': 20,
            'zone': 'us-west-2a',
            'type': 'ebs',
            'profileId': self._profile_id
        }

        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatus(r, 201)
        volume_id = str(r.json['_id'])

        expected = {
            u'name': u'test',
            u'zone': u'us-west-2a',
            u'ec2': {
                u'id': u'vol-1'
            },
            u'type':
            u'ebs',
            u'size': 20,
            u'profileId': self._profile_id
        }

        r = self.request('/volumes/%s' % volume_id, method='GET',
                         type='application/json',
                         user=self._user)
        self.assertStatusOk(r)
        del r.json['_id']
        self.assertEqual(expected, r.json)

        # Try to fetch a volume that doesn't exist
        r = self.request('/volumes/55c3dbd9f65710591baefe60', method='GET',
                         type='application/json',
                         user=self._user)
        self.assertStatus(r, 400)

    @unittest.skip('Skipping until https://github.com/Kitware/cumulus/issues/242 is fixed')
    @mock.patch('girder.plugins.cumulus.models.aws.get_ec2_client')
    def test_delete(self, get_ec2_client):
        volume_id = 'vol-1'
        ec2_client = get_ec2_client.return_value
        ec2_client.create_volume.return_value = {
            'VolumeId': volume_id
        }

        body = {
            'name': 'test',
            'size': 20,
            'zone': 'us-west-2a',
            'type': 'ebs',
            'profileId': self._profile_id
        }

        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatus(r, 201)
        volume = r.json
        volume_id = str(r.json['_id'])

        # Try and delete any attached volume
        ec2_client.describe_volumes.return_value = {
            'Volumes': [{
                'State': 'available'

            }]
        }
        body = {
            'path': '/data'
        }

        url = '/volumes/%s/clusters/%s/attach' % (volume_id, self._cluster_id)
        r = self.request(url, method='PUT',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatusOk(r)

        r = self.request('/volumes/%s' % volume_id, method='DELETE',
                         user=self._user)
        self.assertStatus(r, 400)

        # Detach it then delete it
        ec2_client.describe_volumes.return_value = {
            'Volumes': [{
                'State': 'in-use'

            }]
        }

        url = '/volumes/%s/detach' % (volume_id)
        r = self.request(url, method='PUT', user=self._cumulus)
        self.assertStatusOk(r)

        r = self.request('/volumes/%s' % volume_id, method='DELETE',
                         user=self._user)
        self.assertStatus(r, 200)



    @unittest.skip('Skipping until https://github.com/Kitware/cumulus/issues/242 is fixed')
    @mock.patch('girder.plugins.cumulus.models.aws.get_ec2_client')
    def test_attach_volume(self, get_ec2_client):

        ec2_volume_id = 'vol-1'
        ec2_client = get_ec2_client.return_value
        ec2_client.create_volume.return_value = {
            'VolumeId': ec2_volume_id
        }

        ec2_client.describe_volumes.return_value = {
            'Volumes': [{
                'State': 'available'

            }]
        }
        body = {
            'name': 'test',
            'size': 20,
            'zone': 'us-west-2a',
            'type': 'ebs',
            'fs': 'ext4',
            'profileId': self._profile_id
        }

        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatus(r, 201)
        volume_id = str(r.json['_id'])

        body = {
            'path': '/data'
        }

        url = '/volumes/%s/clusters/%s/attach' % (volume_id, self._cluster_id)
        r = self.request(url, method='PUT',
                         type='application/json', body=json.dumps(body),
                         user=self._user)

        self.assertStatusOk(r)

        r = self.request('/clusters/%s' % self._cluster_id, method='GET',
                         type='application/json', user=self._user)
        self.assertStatusOk(r)

        expected = {
            u'profileId': str(self._profile_id),
            u'status': u'created',
            u'name': u'testing',
            u'userId': str(self._user['_id']),
            u'volumes': [volume_id],
            u'type': u'ec2',
            u'_id': self._cluster_id,
            u'config': {
                u'scheduler': {
                    u'type': u'sge'
                },
                u'ssh': {
                    u'user': u'ubuntu',
                    u'key': str(self._profile_id)
                },
                u'launch': {
                    u'spec': u'default',
                    u'params': {}
                }
            }
        }
        self.assertEqual(r.json, expected)

        # Try to attach volume that is already attached
        ec2_client.reset_mock()
        ec2_client.describe_volumes.return_value = {
            'Volumes': [{
                'State': 'in-use'

            }]
        }

        url = '/volumes/%s/clusters/%s/attach' % (volume_id, self._cluster_id)
        r = self.request(url, method='PUT',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatus(r, 400)

        # Try to attach volume that is currently being created
        ec2_client.reset_mock()
        ec2_client.describe_volumes.return_value = {
            'Volumes': [{
                'State': 'creating'

            }]
        }

        url = '/volumes/%s/clusters/%s/attach' % (volume_id, self._cluster_id)
        r = self.request(url, method='PUT',
                         type='application/json', body=json.dumps(body),
                         user=self._user)

        self.assertStatus(r, 400)
        # Try to attach volume to traditional cluster
        ec2_client.reset_mock()
        ec2_client.describe_volumes.return_value = {
            'Volumes': [{
                'State': 'creating'

            }]
        }

        url = '/volumes/%s/clusters/%s/attach' % (
            volume_id, self._trad_cluster_id)
        r = self.request(url, method='PUT',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatus(r, 400)

    @unittest.skip('Skipping until https://github.com/Kitware/cumulus/issues/242 is fixed')
    @mock.patch('girder.plugins.cumulus.models.aws.get_ec2_client')
    def test_detach_volume(self, get_ec2_client):
        ec2_volume_id = 'vol-1'
        ec2_client = get_ec2_client.return_value
        ec2_client.create_volume.return_value = {
            'VolumeId': ec2_volume_id
        }
        ec2_client.describe_volumes.return_value = {
            'Volumes': [{
                'State': 'available'
            }]
        }

        body = {
            'name': 'testing me',
            'size': 20,
            'zone': 'us-west-2a',
            'type': 'ebs',
            'profileId': self._profile_id
        }

        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatus(r, 201)
        volume_id = str(r.json['_id'])

        # Try detaching volume not in use
        url = '/volumes/%s/detach' % (volume_id)
        r = self.request(url, method='PUT', user=self._user)
        self.assertStatus(r, 400)

        body = {
            'path': '/data'
        }

        url = '/volumes/%s/clusters/%s/attach' % (volume_id, self._cluster_id)
        r = self.request(url, method='PUT',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatusOk(r)

        # Try successful detach
        ec2_client.reset_mock()
        ec2_client.create_volume.return_value = {
            'VolumeId': ec2_volume_id
        }
        ec2_client.describe_volumes.return_value = {
            'Volumes': [{
                'State': 'in-use'
            }]
        }

        url = '/volumes/%s/detach' % (volume_id)
        r = self.request(url, method='PUT', user=self._user)
        self.assertStatusOk(r)

        # Assert that detach was called on ec2 object
        self.assertEqual(len(ec2_client.detach_volume.call_args_list),
                         1, "detach was not called")

        r = self.request('/clusters/%s' % self._cluster_id, method='GET',
                         type='application/json', user=self._cumulus)
        self.assertStatusOk(r)

        expected = {
            u'profileId': str(self._profile_id),
            u'status': u'created',
            u'name': u'testing',
            u'userId': str(self._user['_id']),
            u'volumes': [],
            u'type': u'ec2',
            u'_id': self._cluster_id,
            u'config': {
                u'scheduler': {
                    u'type': u'sge'
                },
                u'ssh': {
                    u'user': u'ubuntu',
                    u'key': str(self._profile_id)
                },
                u'launch': {
                    u'spec': u'default',
                    u'params': {}
                }
            }
        }
        self.assertEqual(r.json, expected)

    @unittest.skip('Skipping until https://github.com/Kitware/cumulus/issues/242 is fixed')
    @mock.patch('girder.plugins.cumulus.models.aws.get_ec2_client')
    def test_find_volume(self, get_ec2_client):
        ec2_volume_id = 'vol-1'
        ec2_client = get_ec2_client.return_value
        ec2_client.create_volume.return_value = {
            'VolumeId': ec2_volume_id
        }
        ec2_client.describe_volumes.return_value = {
            'Volumes': [{
                'State': 'available'
            }]
        }

        # Create some test volumes
        body = {
            'name': 'testing me',
            'size': 20,
            'zone': 'us-west-2a',
            'type': 'ebs',
            'profileId': self._profile_id
        }

        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatus(r, 201)
        volume_1_id = r.json['_id']

        body = {
            'name': 'testing me2',
            'size': 20,
            'zone': 'us-west-2a',
            'type': 'ebs',
            'profileId': self._another_profile_id
        }

        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._another_user)
        self.assertStatus(r, 201)
        volume_2_id = r.json['_id']

        # Search with one user
        r = self.request('/volumes', method='GET', user=self._user)
        self.assertStatusOk(r)
        self.assertEqual(len(r.json), 1, 'Wrong number of volumes returned')
        self.assertEqual(r.json[0]['_id'], volume_1_id, 'Wrong volume returned')

        # Now search with the other
        r = self.request('/volumes', method='GET', user=self._another_user)
        self.assertStatusOk(r)
        self.assertEqual(len(r.json), 1, 'Wrong number of volumes returned')
        self.assertEqual(r.json[0]['_id'], volume_2_id, 'Wrong volume returned')

        # Seach for volumes attached to a particular cluster
        params = {
            'clusterId': self._cluster_id
        }
        r = self.request('/volumes', method='GET', user=self._user,
                         params=params)
        self.assertStatusOk(r)
        self.assertEqual(len(r.json), 0, 'Wrong number of volumes returned')

        body = {
            'path': '/data'
        }

        # Attach a volume
        url = '/volumes/%s/clusters/%s/attach' % (str(volume_1_id), self._cluster_id)
        r = self.request(url, method='PUT',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatusOk(r)

        # Search again
        r = self.request('/volumes', method='GET', user=self._user,
                         params=params)
        self.assertStatusOk(r)
        self.assertEqual(len(r.json), 1, 'Wrong number of volumes returned')

    @unittest.skip('Skipping until https://github.com/Kitware/cumulus/issues/242 is fixed')
    @mock.patch('girder.plugins.cumulus.models.aws.get_ec2_client')
    def test_get_status(self, get_ec2_client):
        ec2_volume_id = 'vol-1'
        ec2_client = get_ec2_client.return_value
        ec2_client.create_volume.return_value = {
            'VolumeId': ec2_volume_id
        }
        ec2_client.describe_volumes.return_value = {
            'Volumes': [{
                'State': 'available'
            }]
        }
        # Create some test volumes
        body = {
            'name': 'testing me',
            'size': 20,
            'zone': 'us-west-2a',
            'type': 'ebs',
            'profileId': self._profile_id
        }

        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatus(r, 201)
        volume_id = str(r.json['_id'])

        # Get status
        url = '/volumes/%s/status' % volume_id
        r = self.request(url, method='GET', user=self._user)
        self.assertStatusOk(r)
        expected = {
            u'status': u'available'
        }
        self.assertEqual(r.json, expected, 'Unexpected status')

        ec2_client.describe_volumes.return_value = {
            'Volumes': [{
                'State': 'in-use'
            }]
        }
        r = self.request(url, method='GET', user=self._user)
        self.assertStatusOk(r)
        expected = {
            u'status': u'in-use'
        }
        self.assertEqual(r.json, expected, 'Unexpected status')

    def test_log(self):
        volume_id = 'vol-1'
        body = {
            'name': 'test',
            'size': 20,
            'zone': 'us-west-2a',
            'type': 'ebs',
            'profileId': self._profile_id
        }

        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatus(r, 201)
        volume_id = str(r.json['_id'])

        # Check that empty log exists for newly created volume
        r = self.request('/volumes/%s/log' % str(volume_id), method='GET',
                         user=self._user)
        self.assertStatusOk(r)
        self.assertEqual(len(r.json['log']), 0)

        log_entry = {
            'msg': 'Some message'
        }

        r = self.request('/volumes/546a1844ff34c70456111185/log', method='GET',
                         user=self._user)
        self.assertStatus(r, 404)

        r = self.request('/volumes/%s/log' % str(volume_id), method='POST',
                         type='application/json', body=json.dumps(log_entry), user=self._user)
        self.assertStatusOk(r)

        r = self.request('/volumes/%s/log' % str(volume_id), method='GET',
                         user=self._user)
        self.assertStatusOk(r)
        expected_log = {u'log': [{u'msg': u'Some message'}]}
        self.assertEqual(r.json, expected_log)

        r = self.request('/volumes/%s/log' % str(volume_id), method='POST',
                         type='application/json', body=json.dumps(log_entry), user=self._user)
        self.assertStatusOk(r)

        r = self.request('/volumes/%s/log' % str(volume_id), method='GET',
                         user=self._user)
        self.assertStatusOk(r)
        self.assertEqual(len(r.json['log']), 2)

        r = self.request('/volumes/%s/log' % str(volume_id), method='GET',
                         params={'offset': 1}, user=self._user)
        self.assertStatusOk(r)
        self.assertEqual(len(r.json['log']), 1)

    def test_volume_sse(self):
        body = {
            'name': 'test',
            'size': 20,
            'zone': 'us-west-2a',
            'type': 'ebs',
            'profileId': self._profile_id
        }

        r = self.request('/volumes', method='POST',
                         type='application/json', body=json.dumps(body),
                         user=self._user)
        self.assertStatus(r, 201)
        volume_id = str(r.json['_id'])

        # connect to volume notification stream
        stream_r = self.request('/notification/stream', method='GET', user=self._user,
                         isJson=False, params={'timeout': 0})
        self.assertStatusOk(stream_r)

        # add a log entry
        log_entry = {
            'msg': 'Some message'
        }
        r = self.request('/volumes/%s/log' % str(volume_id), method='POST',
                         type='application/json', body=json.dumps(log_entry), user=self._user)
        self.assertStatusOk(r)

        notifications = self.getSseMessages(stream_r)

        # we get 2 notifications, 1 from the creation and 1 from the log
        self.assertEqual(len(notifications), 3, 'Expecting two notification, received %d' % len(notifications))
        self.assertEqual(notifications[2]['type'], 'volume.log', 'Expecting a message with type \'volume.log\'')
