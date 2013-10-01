bdsrotater
==========

A Python module for managing a rotation of removable backup disks that
hold a PHD Virtual Backup Appliance Archive block de-duplication store.

Introduction
------------
This script was designed to be run on a Linux NFS server with the
backups disk attached.
When issued "start" the script mounts the removable disk, exports the
VBABACKUPS folder and powers on the VBA.
Conversely, when issued "stop" it shuts down the VBA, unexports the
VBABACKUPS folder and un-mounts the removable disk.
It has only been tested on Debian 7 (Wheezy) with USB3 Removable disk.

Prerequisites
-------------
The removable disks need to have /etc/fstab entries the simplest way to
do this by creating a consistent device node with udev.
    DISK=/dev/sdx
    echo "SUBSYSTEM==\"block\", $(udevadm info -a -p $(udevadm info -q path -n $DISK) | grep ATTRS{serial} | head -n 1 | sed 's/    //'), KERNEL==\"sd?1\", SYMLINK+=\"backupdisk\", GROUP=\"BACKUP\"" >> /etc/udev/rules.d/10-backup-disk.rules


Installation
------------

Download and place the script in your path.

