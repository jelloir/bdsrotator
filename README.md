bdsrotator
==========

A Python module for managing a rotation of removable backup disks that
hold a PHD Virtual Backup Appliance Archive block de-duplication store.

Introduction
------------
This script was designed to be run on a Linux NFS server with the
removeable disk attached.
When issued **_start_** the script mounts the removable disk, exports the
VBABACKUPS folder and powers on the VBA.
Conversely, when issued **_stop_** it shuts down the VBA, unexports the
VBABACKUPS folder and un-mounts the removable disk.
It will email alerts on failures.
It has only been tested on Debian 7 (Wheezy) with USB3 Removable disks.

Prerequisites
-------------

#### Udev Rules For Removeable Disks

Partition and format the removable disks with EXT4 (other file systems
are untested).
The options I use when formatting are:

    mkfs.ext4 /dev/sdxx -E lazy_itable_init=0 -m 0.4 -O ^has_journal

The removable disks need to have `/etc/fstab` entries.  The simplest way
to do this by creating a consistent device node with udev as follows:

Replace the `$DISK` variable with your removable disk.
    
    DISK=/dev/sdx
    echo "SUBSYSTEM==\"block\", $(udevadm info -a -p $(udevadm info -q path -n $DISK) | grep ATTRS{serial} | head -n 1 | sed 's/    //'), KERNEL==\"sd?1\", SYMLINK+=\"backupdisk\", GROUP=\"BACKUP\"" >> /etc/udev/rules.d/10-backup-disk.rules
    udevadm trigger

This appends a rule for the removable disk to:

    /etc/udev/rules.d/10-backup-disk.rules

After running `udevadm trigger` you should see a device node
`/dev/backupdisk` which is a symlink to your actual removeable disk.
Repeat the process for every disk until they are all added.

In `/etc/fstab` you can then create a mount point for all the disks e.g.

    /dev/backupdisk /mnt/backup ext4 rw,noauto,noatime,nodiratime,data=writeback 0 0

#### VBABACKUPS Folder

A dedicated **VBABACKUPS** folder must exist on the root of each
removeable disk.  You can customise this but will need to use the
`--backupdir` argument when running the script.

    mkdir /mnt/backup/VBABACKUPS

#### Python Modules

On Debian Wheezy you will need the following Python Packages.

    apt-get install python-pip python-mailer python2.7

Once installed you also need pysphere which can be installed as follows

    pip install -U pysphere

Installation
------------

Download and place the script in your path and make executable, e.g.

     wget -O /usr/local/bin/bdsrotator.py "https://raw.github.com/jelloir/bdsrotater/master/bdsrotator.py"
     chmod +x /usr/local/bin/bdsrotator.py

Review the help and pay attention to the defaults:

    bdsrotator.py --help

    usage: bdsrotator.py [-h] [-u USERNAME] [-p PASSWORD] [-d BACKUPDISK]
                         [-n NETRCFILE] [-b BACKUPDIR]
                         [-l {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [-e SMTPSENDER]
                         [-r SMTPRECIPIENT] [-t SMTPSERVER] [-s SMTPSUBJECT]
                         [-f NFSOPTS]
                         viserver vaaserver vaaname {start,stop}
    
    positional arguments:
      viserver              vCenter or ESX(i) hostname or IP
      vaaserver             PHD Archive VBA hostname or IP
      vaaname               PHD Archive VBA name in vSphere
      {start,stop}          Start: Mounts and exports USB disk then boots VAA
                            Stop: Shutdown VAA, unexport USB disk and unmount it
    
    optional arguments:
      -h, --help            show this help message and exit
      -u USERNAME, --username USERNAME
                            vCenter or ESX(i) username (default: None)
      -p PASSWORD, --password PASSWORD
                            vCenter or ESX(i) password (default: None)
      -d BACKUPDISK, --backupdisk BACKUPDISK
                            Backup disk mount point (default: /mnt/backup)
      -n NETRCFILE, --netrcfile NETRCFILE
                            Specify location of netrc file (default: ~/.netrc)
      -b BACKUPDIR, --backupdir BACKUPDIR
                            Backup directory on root of backupdisk (default:
                            VBABACKUPS)
      -l {DEBUG,INFO,WARNING,ERROR,CRITICAL}, --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                            set logging level (default: INFO)
      -e SMTPSENDER, --smtpsender SMTPSENDER
                            Sender email address (default:
                            root@nmiavicnas02.nautilus.local)
      -r SMTPRECIPIENT, --smtprecipient SMTPRECIPIENT
                            Recipient email address (default: root)
      -t SMTPSERVER, --smtpserver SMTPSERVER
                            SMTP server address (default: localhost)
      -s SMTPSUBJECT, --smtpsubject SMTPSUBJECT
                            Email Subject (default: bdsrotator on
                            nmiavicnas02.nautilus.local encountered an error)
      -f NFSOPTS, --nfsopts NFSOPTS
                            nfs export options (default:
                            rw,no_root_squash,async,no_subtree_check)

Example Usage
-------------

The script will prompt for a username and/or password in the absense of
a netrc file.  To use a netrc file create it as follows:

    editor ~/.netrc

    machine vcenter.example.local
        login vbadmin
        password mypassword

To mount a disk, export it via NFS to the VBA Archive VM and boot the
VBA Archive VM in it's simplest form:

    bdsrotator.py vcenter.example.local phdvbaarchive.example.local PHDVBAARCHIVE start 

And to perform the opposite...

    bdsrotator.py vcenter.example.local phdvbaarchive.example.local PHDVBAARCHIVE stop

VBA Configuration
-----------------

You will need to prepare a disk and issue a start to bdsrotator.py then
configure the VBA Archive BDS using the the NFS export path .e.g.

    192.168.1.1:/mnt/backup/VBABACKUPS
  
Schedules
---------

I create a crontab entry to start at 18:00 each Mon-Fri and stop at
09:00 each Mon-Fri.  e.g.

    00 09  *   *   1,2,3,4,5 /usr/local/bin/bdsrotator.py vcenter.example.local phdvbaarchive.example.local PHDVBAARCHIVE stop 
    00 18  *   *   1,2,3,4,5 /usr/local/bin/bdsrotator.py vcenter.example.local phdvbaarchive.example.local PHDVBAARCHIVE start
