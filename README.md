# What is this?
This is a simple but powerfull script to backup your EC2 instances using lambda

# How to work?
Cloudwatch Event -> Lambda -> EC2 create ami -> EC2 delete ami -> EC2 delete old snap

# Variables to use
## Lambda Environ
- **BACKUP_RETENTION** = Retention period for delete, value in days (Default: 7, type: int)
- **BACKUP_TAG** = Tag to select the instance to backup (default: BackupIT, type: string)
- **BACKUP_ONLYRUNNING** = Backup the instance if it has the tag and is running (default: false, type: bool)
- **BACKUP_DEBUG** = Verbose script (default: false, type: bool)

## EC2 Tags
- **BackupIT/CUSTOM SETTINGS** = Check BACKUP_TAG
- **BACKUP_COPYTAG** = Copy the tags from EC2 and apply it on AMI snap (default: true, type: bool)
- **BACKUP_REBOOT** = Specify ig you want to restart on AMI snap (default: true, type: bool)


# How to use it?
## Create a IAM roles as below
```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeImages",
                "ec2:DeregisterImage",
                "ec2:DescribeInstances",
                "ec2:DeleteSnapshot",
                "ec2:DescribeTags",
                "ec2:CreateTags",
                "ec2:CreateImage",
                "ec2:DescribeSnapshots"
            ],
            "Resource": "*"
        }
    ]
}
```
## Create a new lambda function
Lambda -> Functions -> Create function -> Author from scratch:

* Name: as you want
* Runtime: Python 3.7
* Role: Select "Create a new role from one or more templates"
* Role name: same as "Name"
-> Create function

Wait until the function is created.
* Copy paste the code into "Function code"
* Change the timeout to 5 min
* Add Cloudwatch Events as below:
  * Rule: "Create a new rule"
  * Rule Name: as you want
  * Rule type: "Schedule expression"
  * Rate: `rate(1 day)`
  * Enable trigger

Add the variables to the EC2 Instances
