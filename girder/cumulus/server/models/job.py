import cherrypy
from girder.models.model_base import AccessControlledModel
from bson.objectid import ObjectId
from girder.constants import AccessType


class Job(AccessControlledModel):

    def initialize(self):
        self.name = 'jobs'

    def validate(self, doc):
        return doc

    def create(self, user, name,  script):
        job = {'name': name, 'script': script, 'status': 'created'}

        doc  = self.setUserAccess(job, user=user, level=AccessType.ADMIN, save=True)

        return str(doc['_id'])

    def status(self, user, id):
        job = self.load(id, user=user, level=AccessType.READ)

        return job['status']

    def update_status(self, user, id, status):
        # Load first to force access check
        self.load(id, user=user, level=AccessType.ADMIN)
        return self.update({'_id': ObjectId(id)}, {'$set': {'status': status}})

    def set_sge_job_id(self, user, id, job_id):
        # Load first to force access check
        self.load(id, user=user, level=AccessType.ADMIN)
        return self.update({'_id': ObjectId(id)}, {'$set': {'sgeJobId': job_id}})
