import cherrypy
import json

import cumulus
import cumulus.aws.ec2.tasks.key

from cumulus.common.girder import get_task_token
from cumulus.starcluster.common import get_easy_ec2

from girder.api import access
from girder.api.describe import Description
from girder.constants import AccessType
from girder.api.docs import addModel
from girder.api.rest import RestException, getBodyJson, ModelImporter,\
    getCurrentUser
from girder.api.rest import loadmodel


def requireParams(required, params):
    for param in required:
        if param not in params:
            raise RestException("Parameter '%s' is required." % param)


def _filter(profile):
    del profile['access']
    profile = json.loads(json.dumps(profile, default=str))

    return profile


@access.user
@loadmodel(model='user', level=AccessType.WRITE)
def create_profile(user, params):
    body = getBodyJson()
    requireParams(['name', 'accessKeyId', 'secretAccessKey', 'regionName',
                   'availabilityZone'], body)

    model = ModelImporter.model('aws', 'cumulus')
    profile = model.create_profile(user['_id'], body['name'],
                                   body['accessKeyId'],
                                   body['secretAccessKey'], body['regionName'],
                                   body['availabilityZone'],
                                   body.get('publicIPs', False))

    # Now fire of a task to create a key pair for this profile
    try:
        cumulus.aws.ec2.tasks.key.generate_key_pair.delay(
            _filter(profile), get_task_token()['_id'])

        cherrypy.response.status = 201
        cherrypy.response.headers['Location'] \
            = '/user/%s/aws/profile/%s' % (str(user['_id']),
                                           str(profile['_id']))

        return model.filter(profile, getCurrentUser())
    except Exception:
        # Remove profile if error occurs fire of task
        model.remove(profile)
        raise


addModel('AwsParameters', {
    'id': 'AwsParameters',
    'required': ['name', 'accessKeyId', 'secretAccessKey', 'regionName',
                 'regionHost', 'availabilityZone'],
    'properties': {
        'name': {'type': 'string',
                 'description': 'The name of the profile.'},
        'accessKeyId':  {'type': 'string',
                         'description': 'The aws access key id'},
        'secretAccessKey': {'type': 'string',
                            'description': 'The aws secret access key'},
        'regionName': {'type': 'string',
                       'description': 'The aws region'},
        'availabilityZone': {'type': 'string',
                             'description': 'The aws availablility zone'}
    }
}, 'user')

create_profile.description = (
    Description('Create a AWS profile')
    .param('id', 'The id of the user', required=True, paramType='path')
    .param(
        'body',
        'The properties to use to create the profile.',
        dataType='AwsParameters',
        required=True, paramType='body'))


@access.user
@loadmodel(model='user', level=AccessType.READ)
@loadmodel(model='aws', plugin='cumulus',  map={'profileId': 'profile'},
           level=AccessType.WRITE)
def delete_profile(user, profile, params):

    query = {
        'aws': {
            'profileId': profile['_id']
        }
    }

    if ModelImporter.model('volume', 'cumulus').findOne(query):
        raise RestException('Unable to delete profile as it is associated with'
                            ' a volume', 400)

    if ModelImporter.model('starclusterconfig', 'cumulus').findOne(query):
        raise RestException('Unable to delete profile as it is associated with'
                            ' a configuration', 400)

    # Clean up key associate with profile
    cumulus.aws.ec2.tasks.key.delete_key_pair.delay(_filter(profile),
                                                    get_task_token()['_id'])

    ec2 = get_easy_ec2(profile)
    ec2.delete_keypair(profile['_id'])

    ModelImporter.model('aws', 'cumulus').remove(profile)


delete_profile.description = (
    Description('Delete an aws profile')
    .param('id', 'The id of the user', required=True, paramType='path')
    .param('profileId', 'The id of the profile to delete', paramType='path',
           required=True))


@access.user
@loadmodel(model='user', level=AccessType.READ)
@loadmodel(model='aws', plugin='cumulus',  map={'profileId': 'profile'},
           level=AccessType.WRITE)
def update_profile(user, profile, params):
    body = getBodyJson()
    properties = ['accessKeyId', 'secretAccessKey', 'status', 'errorMessage',
                  'publicIPs']
    for prop in properties:
        if prop in body:
            profile[prop] = body[prop]

    ModelImporter.model('aws', 'cumulus').update_aws_profile(getCurrentUser(),
                                                             profile)

addModel('AwsUpdateParameters', {
    'id': 'AwsUpdateParameters',
    'properties': {
        'accessKeyId':  {'type': 'string',
                         'description': 'The aws access key id'},
        'secretAccessKey': {'type': 'string',
                            'description': 'The aws secret access key'},
        'status': {'type': 'string',
                   'description': 'The status of this profile, if its ready'
                   ' to use'},
        'errorMessage': {'type': 'string',
                         'description': 'A error message if a error occured '
                         'during the creation of this profile'}
    }
}, 'user')

update_profile.description = (
    Description('Update a AWS profile')
    .param('id', 'The id of the user', required=True, paramType='path')
    .param('profileId', 'The id of the profile to update', required=True,
           paramType='path')
    .param(
        'body',
        'The properties to use to update the profile.',
        dataType='AwsUpdateParameters',
        required=True, paramType='body'))


@access.user
@loadmodel(model='user', level=AccessType.READ)
def get_profiles(user, params):
    user = getCurrentUser()
    model = ModelImporter.model('aws', 'cumulus')
    limit = params.get('limit', 50)
    profiles = model.find_profiles(user['_id'])

    profiles = model.filterResultsByPermission(profiles, user, AccessType.READ,
                                               limit=int(limit))

    return [model.filter(profile, user) for profile in profiles]

get_profiles.description = (
    Description('Get the AWS profiles for a user')
    .param('id', 'The id of the user', required=True, paramType='path'))


@access.user
@loadmodel(model='user', level=AccessType.READ)
@loadmodel(model='aws', plugin='cumulus',  map={'profileId': 'profile'},
           level=AccessType.WRITE)
def status(user, profile, params):
    return {
        'status': profile['status']
    }

addModel('AwsProfileStatus', {
    'id': 'AwsProfileStatus',
    'required': ['status'],
    'properties': {
        'status': {'type': 'string',
                   'enum': ['creating', 'available', 'error']}
    }
}, 'user')

status.description = (
    Description('Get the status of this profile.')
    .param('id', 'The id of the user', paramType='path')
    .param('profileId', 'The id of the profile to update', required=True,
           paramType='path')
    .responseClass('AwsProfileStatus'))


@access.user
@loadmodel(model='user', level=AccessType.READ)
@loadmodel(model='aws', plugin='cumulus',  map={'profileId': 'profile'},
           level=AccessType.WRITE)
def running_instances(user, profile, params):
    ec2 = get_easy_ec2(profile)
    count = ec2.get_running_instance_count()

    return {
        'runninginstances': count
    }

addModel('AwsProfileRunningInstances', {
    'id': 'AwsProfileRunningInstances',
    'required': ['runninginstances'],
    'properties': {
        'runninginstances': {'type': 'integer'}
    }
}, 'user')

running_instances.description = (
    Description('Get the number of running instances')
    .param('id', 'The id of the user', paramType='path')
    .param('profileId', 'The id of the profile to update', required=True,
           paramType='path')
    .responseClass('AwsProfileRunningInstances'))


@access.user
@loadmodel(model='user', level=AccessType.READ)
@loadmodel(model='aws', plugin='cumulus',  map={'profileId': 'profile'},
           level=AccessType.WRITE)
def max_instances(user, profile, params):
    ec2 = get_easy_ec2(profile)
    count = ec2.get_max_instances()

    return {
        'maxinstances': count
    }

addModel('AwsProfileMaxInstances', {
    'id': 'AwsProfileRunningInstances',
    'required': ['runninginstances'],
    'properties': {
        'maxinstances': {'type': 'integer'}
    }
}, 'user')

max_instances.description = (
    Description('Get the maximum number of instance this account can run')
    .param('id', 'The id of the user', paramType='path')
    .param('profileId', 'The id of the profile to update', required=True,
           paramType='path')
    .responseClass('AwsProfileMaxInstances'))


def load(apiRoot):
    apiRoot.user.route('POST', (':id', 'aws', 'profiles'), create_profile)
    apiRoot.user.route('DELETE', (':id', 'aws', 'profiles', ':profileId'),
                       delete_profile)
    apiRoot.user.route('PATCH', (':id', 'aws', 'profiles', ':profileId'),
                       update_profile)
    apiRoot.user.route('GET', (':id', 'aws', 'profiles'), get_profiles)
    apiRoot.user.route('GET', (':id', 'aws', 'profiles', ':profileId',
                               'status'), status)
    apiRoot.user.route('GET', (':id', 'aws', 'profiles', ':profileId',
                               'runninginstances'), running_instances)
    apiRoot.user.route('GET', (':id', 'aws', 'profiles', ':profileId',
                               'maxinstances'), max_instances)
