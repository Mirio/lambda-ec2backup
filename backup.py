# Source: https://github.com/Mirio/lambda-ec2Backup
# License: GPL-3.0
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
from os import getenv
from sys import exit
import logging
import boto3

## Setup logging
log = logging.getLogger()
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
for handler in log.handlers:
    handler.setFormatter(logging.Formatter(log_format))
if getenv("BACKUP_DEBUG") == "true":
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.INFO)

class LambdaEc2Backup(object):
    def __init__(self):
        ## Check if region is set
        self.region = getenv("AWS_REGION")
        self.retentiondays = int(getenv("BACKUP_RETENTION", 7))
        self.ec2tag = getenv("BACKUP_TAG", "BackupIT")
        if getenv("BACKUP_ONLYRUNNING") == "true":
            self.ec2onlyrun = True
        else:
            self.ec2onlyrun = False
        log.debug(
            "Show Settings: REGION=%s BACKUP_RETENTION=%s BACKUP_TAG=%s "
            "BACKUP_ONLYRUNNING=%s" % (
                self.region, self.retentiondays, self.ec2tag,
                self.ec2onlyrun))

        self.botoclient = boto3.client('ec2')
        self.ownerid = boto3.client('sts').get_caller_identity()['Account']

    def createimage(self, instanceid, tags):
        """
        Create an image from instance
        :params instanceid: instance id (string)
        :params tags: tags taken from instance to snap (list)
        :return: None
        """
        instancename = ""
        rebootflag = True
        ec2copytag = True
        log.info("Creating image from '%s'" % instanceid)
        for tagiter in tags:
            if tagiter["Key"] == "Name":
                instancename = tagiter["Value"]
            if tagiter["Key"] == "BACKUP_REBOOT":
                if tagiter["Value"] == "false":
                    rebootflag = False
                else:
                    rebootflag = True
            if tagiter["Key"] == "BACKUP_COPYTAG":
                if tagiter["Value"] == "false":
                    ec2copytag = False
                else:
                    ec2copytag = True
        ## Force instance name to instanceid
        if not instancename:
            instancename = instanceid
        ec2reso = boto3.resource('ec2')
        instance = ec2reso.Instance(id=instanceid)
        ## Check if instance exists
        try:
            log.debug("Checking if the instance '%s' exists" % instanceid)
            instance.load()
        except ClientError as e:
            log.error(e)
            log.debug("Skipped.")
            return
        # Format useful for sorting
        now = datetime.now()
        deleteon = (now+timedelta(days=7)).strftime("%Y-%m-%d")
        imagename = "%s-LEB-%s" % (now.strftime("%Y%m%d_%H%M"),
                                   instancename)
        req = self.botoclient.create_image(InstanceId=instanceid,
                                           Name=imagename,
                                           NoReboot=(not rebootflag),
                                           Description="Snap create by LEB"
                                                   "(https://github.com/Mirio/"
                                                   "lambda-ec2backup)")
        log.debug("Creating image..")
        # Waiting until image is available
        imagereso = ec2reso.Image(id=req["ImageId"])
        imagereso.wait_until_exists()
        tags_toapply = [
            {"Key": "LEB-DeleteOn", "Value": deleteon},
            {"Key": "InstanceNameFrom", "Value": instancename},
            {"Key": "Name", "Value": instancename},
        ]
        if ec2copytag:
            for tagsiter in tags:
                tags_toapply.append(tagsiter)
        log.debug("Apply Tags")
        imagereso.create_tags(Tags=tags_toapply)
        log.info("Image from '%s' created and tags applied." % instanceid)
        return

    def listinstance(self, maxresults=1000):
        """
        Return a list of instances matched
        :param maxresults: max number of instances per query (int)
        :returns: [{'id': <foo id (string)>,"tags": ["foo",]},]
        """
        instances = []
        filters = [{"Name": "tag-key", "Values": [self.ec2tag]}]

        if self.ec2onlyrun:
            filters.append({"Name": "instance-state-name",
                            "Values": ["running"]})
        else:
            filters.append({"Name": "instance-state-name",
                            "Values": ["running", "stopped"]})
        try:
            req = self.botoclient.describe_instances(MaxResults=maxresults,
                                                     Filters=filters)
        except ClientError as e:
            log.critical(e)
            exit(1)
        for instanceiter in req["Reservations"][0]["Instances"]:
            instances.append({
                "id": instanceiter["InstanceId"],
                "tags": instanceiter["Tags"]
            })
        return instances

    def listamis(self):
        """
        Return a list of images to delete with self.ec2tag
        :returns: [{'id': <foo id (string)>, "tags": ["foo",]},]
        """
        amis = []
        filters = [{"Name": "tag-key", "Values": [self.ec2tag]}]
        try:
            req = self.botoclient.describe_images(Filters=filters)
        except ClientError as e:
            log.critical(e)
            exit(1)
        now = datetime.now()
        for imageiter in req["Images"]:
            for tagiter in imageiter["Tags"]:
                if tagiter["Key"] == "LEB-DeleteOn":
                    if datetime.strptime(tagiter["Value"],
                                         "%Y-%m-%d") <= datetime.now():
                        amis.append({
                            "id": imageiter["ImageId"],
                            "tags": imageiter["Tags"]
                        })
        return amis

    def listsnap(self, ami_id, maxresults=1000):
        """
        Return an list of snapshot created by AMIs specified
        :params ami_id: AMI id source (string)
        :returns: list of snapshot related to the ami_id (list)
        """
        snaps = []
        try:
            req = self.botoclient.describe_snapshots(MaxResults=maxresults,
                                                     OwnerIds=[self.ownerid])
        except ClientError as e:
            log.critical(e)
            exit(1)
        for snap in req["Snapshots"]:
            if ami_id in snap["Description"]:
                snaps.append(snap["SnapshotId"])
        return snaps


    def deletesnap(self, snapid):
        """
        Delete a snapshot
        :params snapid: Snapshot id (string)
        :returns: None
        """
        ec2reso = boto3.resource('ec2')
        snapshot = ec2reso.Snapshot(snapid)
        snapshot.delete()
        log.info("Snapshot %s deleted." % snapid)

    def deleteami(self, imageid):
        """
        Delete an image
        :params imageid: AMI to delete (string)
        :returns: None
        """
        ec2reso = boto3.resource('ec2')
        imagereso = ec2reso.Image(id=imageid)
        imagereso.deregister()
        log.info("Image %s deleted." % imageid)
        return


    def run(self):
        # Create AMIs
        for instanceiter in self.listinstance():
            self.createimage(instanceid=instanceiter["id"],
                             tags=instanceiter["tags"])

        # Cleanup AMIs
        for image in self.listamis():
            log.debug("Checking '%s'" % image)
            listsnap = self.listsnap(ami_id=image["id"])
            self.deleteami(imageid=image["id"])
            for snap in listsnap:
                self.deletesnap(snapid=snap)


def lambda_handler(event, context):
    """ Lambda Handler """
    obj = LambdaEc2Backup()
    obj.run()
    return
