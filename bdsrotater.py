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
from mailer import Mailer
from mailer import Message


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


def export_bds(vaaserver, bupath, nfsopts):
    """Export bupath to vaaserver."""
    #https://bugzilla.redhat.com/show_bug.cgi?id=966237
    subprocess.check_call([exportfs, '-o', nfsopts, vaaserver + ':' + bupath])
    logging.debug('Exported %s succesfully to %s', bupath, vaaserver)
    return


def unexport_bds(vaaserver, bupath):
    """Unexport bupath to vaaserver."""
    subprocess.check_call([exportfs, '-u', vaaserver + ':' + bupath])
    logging.debug('Unexported %s succesfully from %s', bupath, vaaserver)
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
        export_bds(args.vaaserver, bupath, args.nfsopts)
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
    viauthtoken = None
    bupath = os.path.join(args.backupdisk, args.backupdir)
    username, password = get_credentials(args.username, args.password, args.netrcfile, args.viserver)

    try:
        viauthtoken = connect_viserver(args.viserver, username, password)
    except Exception as e:
        raise

    try:
        vaa_shutdown(args.vaaname, viauthtoken)
    except Exception as e:    
        try:
            raise
        finally:
            # Need to unexport dir before this - how? in context of cleanup?
            cleanup(args.backupdisk)

    try:
        unexport_bds(args.vaaserver, bupath)
    except (OSError, subprocess.CalledProcessError) as e:
        try:
            raise
        finally:
            cleanup(args.backupdisk)

    try:
        umount_usb(args.backupdisk)
    except (OSError, subprocess.CalledProcessError) as e:
        raise

    return


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


def body_creator(log_file):
    body = []
    for line in open(log_file):
        body.append(line)
    return body


def relay_email(smtpserver, smtprecipient, smtpsender, smtpsubject, body):
    b = ''.join(body)
    message = Message(From=smtpsender, To=smtprecipient, Subject=smtpsubject)
    message.Body = b
    sender = Mailer(smtpserver)
    sender.send(message)

  
def main():

    log_file = '/var/log/vaactl.log'

    """Setup argparse."""
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)

    """Positional arguments."""
    parser.add_argument('viserver',
        help='vCenter or ESX(i) hostname or IP')

    parser.add_argument('vaaserver',
        help='PHD Virtual Backup Archive Appliance hostname or IP')

    parser.add_argument('vaaname',
        help='PHD Virtual Archive Appliance name in vSphere')

    parser.add_argument('process', choices=['start', 'stop'],
        help='Start: Mounts and exports USB disk then boots VAA\nStop: Shutdown VAA, unexport USB disk and unmount it')

    """Optional arguments."""
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

    whoatnode = getpass.getuser() + '@' + platform.node()
    parser.add_argument('-e', '--smtpsender',
        help='Sender email address\ndefault = %s' %(whoatnode),
        default=whoatnode)

    who = getpass.getuser()
    parser.add_argument('-r', '--smtprecipient',
        help='Recipient email address\ndefault = %s' %(who),
        default=who)

    parser.add_argument('-t', '--smtpserver',
        help='SMTP server address\ndefault = localhost',
        default='localhost')

    host = platform.node()
    parser.add_argument('-s', '--smtpsubject',
        help='Email Subject Line\ndefault = Alert! BDSROTATOR on %s encountered an error' %(host),
        default='Alert! BDSROTATOR on %s encountered an error' %(host))

    parser.add_argument('-f', '--nfsopts',
        help='nfs export options\ndefault = rw,no_root_squash,async,no_subtree_check',
        default='rw,no_root_squash,async,no_subtree_check')

    """Create variables from argparse."""
    args = parser.parse_args()

    logging.basicConfig(
        filename=log_file, format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%F %H:%M:%S', filemode='w',
        level=args.log_level)

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
        except Exception as ee:
            logging.error(ee)
            try:
                body = body_creator(log_file)
                relay_email(args.smtpserver, args.smtprecipient, args.smtpsender, args.smtpsubject, body)
            except Exception as emailerr:
                logging.error(emailerr)
            finally:
                return 1

    if args.process == 'stop':
        try:
            stop(args)
            return 0
        except Exception as ee:
            logging.error(ee)
            try:
                body = body_creator(log_file)
                relay_email(args.smtpserver, args.smtprecipient, args.smtpsender, args.smtpsubject, body)
            except Exception as emailerr:
                logging.error(emailerr)
            finally:
                return 1


if __name__ == '__main__':
    sys.exit(main())

