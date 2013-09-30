#!/usr/bin/env python

from pysphere import VIServer
from distutils.spawn import find_executable
from time import sleep
import os
import sys
import subprocess
import argparse
import logging
import netrc
import platform
import getpass


class CheckUsbError(Exception):
    pass

class FindExeError(Exception):
    pass


def sync_buffers():
    """Force changed blocks to disk."""
    subprocess.check_call(sync)
    logging.debug('Sync buffers successful.')
    return


def mount_usb(backupdisk):
    """Mount backupdisk."""
    subprocess.check_call([mount, backupdisk])
    logging.debug('Mounted %s successfully.', backupdisk)        
    return


def check_usb(bupath):
    """Test backupdir exists and is rw on backupdisk."""
    if not os.path.isdir(bupath):
        raise CheckUsbError('%s not found.' %(bupath))
    if not os.access(bupath, os.W_OK|os.R_OK):
        raise CheckUsbError('%s is not writeable.' %(bupath))
    logging.debug('Backup disk validation passed.')
    return


def umount_usb(backupdisk):
    """Unmount backupdisk."""
    subprocess.check_call([umount, backupdisk])
    logging.debug('Unmounted %s successfully.', backupdisk)
    return


def export_bds(nfsclient, bupath, nfsopts):
    """Export bupath to nfsclient."""
    #https://bugzilla.redhat.com/show_bug.cgi?id=966237
    subprocess.check_call([exportfs, '-o', nfsopts, nfsclient + ':' + bupath])
    logging.debug('Exported %s succesfully to %s', bupath, nfsclient)
    return


def unexport_bds(nfsclient, bupath):
    """Unexport bupath to nfsclient."""
    subprocess.check_call([exportfs, '-u', nfsclient + ':' + bupath])
    logging.debug('Unexported %s succesfully from %s', bupath, nfsclient)
    return


def connect_viserver(viserver, username, password):
    server = VIServer()
    server.connect(viserver, username, password)
    logging.info('Connected to %s succesfully', viserver)
    return server


def vaa_poweron(vaaname, viauthtoken):
    vaa = viauthtoken.get_vm_by_name(vaaname)
    if vaa.is_powered_on():
        vaa.reboot_guest()
    else:
        if vaa.is_powered_off():
            vaa.power_on()
    return


def vaa_shutdown(vaaname, viauthtoken):
    vaa = viauthtoken.get_vm_by_name(vaaname)
    if vaa.is_powered_on():
        vaa.shutdown_guest()
    return


def get_credentials(username, password, netrcfile, viserver):
    """
    Return username and password if set else prompt for username or
    password if one set without the other else use netrc else prompt for
    username and password.
    """
    if username and password:
         return username, password
    if username and not password:
         password = getpass.getpass()
         return username, password
    if password and not username:
         print 'Username: ',
         username = sys.stdin.readline()[:-1]
         return username, password
    if netrcfile:
         info = netrc.netrc()
         cred = info.authenticators(viserver)
         if cred:
             return (cred[0], cred[2])
             logging.info("Could not find credentials in netrc file.")
    if not username and not password:
         print 'Username: ',
         username = sys.stdin.readline()[:-1]
         password = getpass.getpass()
         return username, password


def start(args):
    viauthtoken = None
    bupath = os.path.join(args.backupdisk, args.backupdir)
    username, password = get_credentials(args.username, args.password, args.netrcfile, args.viserver)

    try:
        viauthtoken = connect_viserver(args.viserver, username, password)
    except Exception as e:
        raise

    try:
        backupdisk_mounted = os.path.ismount(args.backupdisk)
        if not backupdisk_mounted:
            logging.debug('Attempting to mount %s', args.backupdisk)
            mount_usb(args.backupdisk)
            #mounted_usb_ok = True
        else:
            logging.debug('%s already mounted', args.backupdisk)
    except (OSError, subprocess.CalledProcessError) as e:
        raise

    try:
        check_usb(bupath)
    except (OSError, CheckUsbError) as e:
        try:
            raise
        finally:
            cleanup(args.backupdisk)

    try:
        export_bds(args.nfsclient, bupath, args.nfsopts)
    except (OSError, subprocess.CalledProcessError) as e:
        try:
            raise
        finally:
            cleanup(args.backupdisk)

    try:
        vaa_poweron(args.vaaname, viauthtoken)
    except Exception as e:    
        try:
            raise
        finally:
            cleanup(args.backupdisk)
    return        

def stop(args):
    print 'Null'

def cleanup(backupdisk):
    """Cleanup log and pass any exceptions from cleanup"""
    try:
        sync_buffers()
    except Exception as e:
        logging.error(e)
        pass

    try:
        umount_usb(backupdisk)
    except Exception as e:
        logging.error(e)
        pass    

  
def main():

    log_file = '/var/log/vaactl.log'

    """Setup argparse."""
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)

#    parser.add_argument('-s', '--viserver',
#        help='vCenter or ESX(i) hostname or IP',
#        required=True)
#
#    parser.add_argument('-i', '--vaaserver',
#        help='PHD Virtual Archive Appliance hostname or IP',
#        required=True)
#
#    parser.add_argument('-a', '--vaaname',
#        help='PHD Virtual Archive Appliance name in vSphere',
#        required=True)

    parser.add_argument('viserver',
        help='vCenter or ESX(i) hostname or IP')

    parser.add_argument('process', choices=['start', 'stop'],
        help='Start: Mounts and exports USB disk then boots VAA\nStop: Shutdown VAA, unexport USB disk and unmount it')

    parser.add_argument('-u', '--username',
        help='vCenter or ESX(i) username',
        default=None)

    parser.add_argument('-p', '--password',
        help='vCenter or ESX(i) password',
        default=None)

    parser.add_argument('-d', '--backupdisk',
        help='Backup disk mount point\ndefault = /mnt/backup',
        default='/mnt/backup')

    parser.add_argument('-n', '--netrcfile',
        help='Specify location of netrc file\ndefault = ~/.netrc',
        default='~/.netrc')

    parser.add_argument('-b', '--backupdir',
        help='Backup directory on root of backupdisk\ndefault = VBABACKUPS',
        default='VBABACKUPS')

    parser.add_argument('-l', '--log-level',
        help='set logging level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])

    parser.add_argument('-e', '--smtpsender',
        help='Sender email address\ndefault = $USER@$HOSTNAME',
        default=getpass.getuser() + '@' + platform.node())

    parser.add_argument('-r', '--smtprecipient',
        help='Sender email address\ndefault = $USER',
        default=getpass.getuser())

    parser.add_argument('-t', '--smtpserver',
        help='Sender email address\ndefault = localhost',
        default='localhost')

    parser.add_argument('-f', '--nfsopts',
        help='nfs export options\ndefault = rw,no_root_squash,async,no_subtree_check',
        default='rw,no_root_squash,async,no_subtree_check')

    """Create variables from argparse."""
    args = parser.parse_args()

    logging.basicConfig(
        filename=log_file, format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%F %H:%M:%S', filemode='w',
        level=log_level)

    """Agnostically obtain paths for exes."""
    global rsync, sync, mount, umount, exportfs
    ospaths = '/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin'
    rsync = find_executable('rsync', path=ospaths)
    sync = find_executable('sync', path=ospaths)
    mount = find_executable('mount', path=ospaths)
    umount = find_executable('umount', path=ospaths)
    exportfs = find_executable('exportfs', path=ospaths)
    try:
        if not rsync:
            raise FindExeError('rsync executable not found, is it installed?')
        if not exportfs:
            raise FindExeError('exportfs executable not found, is it installed?')
        if not sync:
            raise FindExeError('sync executable not found.')
        if not mount:
            raise FindExeError('mount executable not found.')
        if not umount:
            raise FindExeError('umount executable not found.')
    except FindExeError as e:
        logging.error(e)
        return 1
    

    if args.process == 'start':
        try:
            start(args)
            return 0
        # Catch any unspecified exceptions
        except Exception as ee:
            logging.error(ee)
            return 1


if __name__ == '__main__':
    sys.exit(main())

