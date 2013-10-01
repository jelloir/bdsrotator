bdsrotater
==========

A Python module for managing a rotation of removable backup disks that
hold a PHD Virtual Backup Appliance Archive block de-duplication store.

Introduction
------------
This script was designed to be run on a Linux NFS server with the
backups disk attached.
When issued **_start_** the script mounts the removable disk, exports the
VBABACKUPS folder and powers on the VBA.
Conversely, when issued **_stop_** it shuts down the VBA, unexports the
VBABACKUPS folder and un-mounts the removable disk.
It has only been tested on Debian 7 (Wheezy) with USB3 Removable disk.

Prerequisites
-------------
Partition and format the removable disks with EXT4 (other file systems
are untested).
The options I use when formatting are:

    mkfs.ext4 /dev/sdxx -E lazy_itable_init=0 -m 0.4 -O ^has_journal

The removable disks need to have `/etc/fstab` entries the simplest way to
do this by creating a consistent device node with udev.  Replace `$DISK`
variable with your removable disk.
    
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




Installation
------------

Download and place the script in your path.

