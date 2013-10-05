#!/usr/bin/env python

import argparse
import getpass
import logging
import netrc
import os
import platform
import subprocess
import sys
import traceback
from distutils.spawn import find_executable
from mailer import Mailer
from mailer import Message
from pysphere import VIServer


class BackupdiskAlreadyMounted(Exception):
    pass

class CheckBDSError(Exception):
    pass

class FindExeError(Exception):
    pass

class PowerState(Exception):
    pass

class ExistingExport(Exception):
    pass


def sync_buffers():
    """Force changed blocks to disk."""
    subprocess.check_call(sync)
    logging.debug('Sync buffers successful.')
    return


def mnt_removeable(backupdisk):
    """Mount backupdisk."""
    if os.path.ismount(backupdisk):
        raise BackupdiskAlreadyMounted('%s already mounted, is this expected?' %(backupdisk))
    else:
        subprocess.check_call([mount, backupdisk])
        logging.debug('Mounted %s successfully.', backupdisk)        
        return False


def check_bds(bdspath):
    """Test bdsdir exists and is rw on backupdisk."""
    if not os.path.isdir(bdspath):
        raise CheckBDSError('%s not found.' %(bdspath))
    if not os.access(bdspath, os.W_OK|os.R_OK):
        raise CheckBDSError('%s is not writeable.' %(bdspath))
    logging.debug('Backup disk validation passed.')
    return


def unmnt_removeable(backupdisk):
    """Unmount backupdisk."""
    subprocess.check_call([umount, backupdisk])
    logging.debug('Unmounted %s successfully.', backupdisk)
    return


def export_bds(avbaserver, bdspath, nfsopts):
    """Export bdspath to avbaserver."""
    nfsmounts = subprocess.check_output([showmount, '-e', '--no-headers']).splitlines()
    for item in nfsmounts:
        if item.startswith(bdspath):
            raise ExistingExport('%s is already exported according to showmount' %(bdspath))
    #https://bugzilla.redhat.com/show_bug.cgi?id=966237
    subprocess.check_call([exportfs, '-o', nfsopts, avbaserver + ':' + bdspath])
    logging.debug('Exported %s successfully to %s', bdspath, avbaserver)
    return


def unexport_bds(avbaserver, bdspath):
    """Unexport bdspath to avbaserver."""
    subprocess.check_call([exportfs, '-u', avbaserver + ':' + bdspath])
    logging.debug('Unexported %s successfully from %s', bdspath, avbaserver)
    return


def connect_viserver(viserver, username, password):
    """Connect to viserver and return viauthtoken"""
    server = VIServer()
    server.connect(viserver, username, password)
    logging.info('Connected to %s successfully', viserver)
    return server


def avba_poweron(avbaname, viauthtoken):
    """Poweron Archive VBA"""
    avba = viauthtoken.get_vm_by_name(avbaname)
    if avba.is_powered_on():
        raise PowerState('%s already powered on!' %(avbaname))
    else:
        if avba.is_powered_off():
            avba.power_on()
            logging.info('%s poweron initiated', avbaname)
    return


def avba_shutdown(avbaname, viauthtoken):
    """Shutdown Archive VBA"""
    avba = viauthtoken.get_vm_by_name(avbaname)
    if avba.is_powered_on():
        avba.shutdown_guest()
        logging.info('%s shutdown initiated', avbaname)
    else:
        raise PowerState('%s was not in powered on state!' %(avbaname))
    return


def get_credentials(username, password, netrcfile, viserver):
    """
    Returns username and password if set else prompts for username or
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
    bdspath = os.path.join(args.backupdisk, args.bdsdir)
    username, password = get_credentials(args.username, args.password, args.netrcfile, args.viserver)
    result = True

    try:
        viauthtoken = connect_viserver(args.viserver, username, password)
    except Exception as e:
        raise

    try:
        backupdisk_already_mounted = True
        backupdisk_already_mounted = mnt_removeable(args.backupdisk)
    except BackupdiskAlreadyMounted as e:
        logging.warning(e)
        result = False
    except (OSError, subprocess.CalledProcessError) as e:
        raise

    try:
        check_bds(bdspath)
    except (OSError, CheckBDSError) as e:
        try:
            raise
        finally:
            if not backupdisk_already_mounted:
                try:
                    sync_buffers()
                except Exception as sync_buffers_e:
                    logging.error(sync_buffers_e)
                    pass
                try:
                    unmnt_removeable(args.backupdisk)
                except Exception as unmnt_removeable_e:
                    logging.error(unmnt_removeable_e)
                    pass    

    try:
        export_bds(args.avbaserver, bdspath, args.nfsopts)
    except ExistingExport as e:
        # Should we run command to reexport/flush if we get this far to ensure nfs is working?
        logging.warning(e)
        result = False
    except (OSError, subprocess.CalledProcessError) as e:
        try:
            raise
        finally:
            if not backupdisk_already_mounted:
                try:
                    sync_buffers()
                except Exception as sync_buffers_e:
                    logging.error(sync_buffers_e)
                    pass
                try:
                    unmnt_removeable(args.backupdisk)
                except Exception as unmnt_removeable_e:
                    logging.error(unmnt_removeable_e)
                    pass    

    try:
        avba_poweron(args.avbaname, viauthtoken)
    except PowerState as e:
        logging.warning(e)
        result = False
    except Exception as e:    
        try:
            raise
        finally:
            logging.warning('VBA poweron error! Attempting cleanup.')
            if not backupdisk_already_mounted:
                try:
                    unexport_bds(args.avbaserver, bdspath)
                except Exception as unexport_bds_e:
                    logging.error(unexport_bds_e)
                    pass
                try:
                    sync_buffers()
                except Exception as sync_buffers_e:
                    logging.error(sync_buffers_e)
                    pass
                try:
                    unmnt_removeable(args.backupdisk)
                except Exception as unmnt_removeable_e:
                    logging.error(unmnt_removeable_e)
                    pass
            else:
                try:
                    unexport_bds(args.avbaserver, bdspath)
                except Exception as unexport_bds_e:
                    logging.error(unexport_bds_e)
                    pass

    if not result:
        raise Exception('Warning encountered during start process!')
    return        


def stop(args):
    viauthtoken = None
    bdspath = os.path.join(args.backupdisk, args.bdsdir)
    username, password = get_credentials(args.username, args.password, args.netrcfile, args.viserver)
    result = True

    try:
        viauthtoken = connect_viserver(args.viserver, username, password)
    except Exception as e:
        raise

    try:
        avba_shutdown(args.avbaname, viauthtoken)
    except PowerState as e:
        logging.warning(e)
        result = False        
    except Exception as e:    
        try:
            raise
        finally:
            logging.warning('VBA shutdown error! Attempting cleanup.')
            try:
                unexport_bds(args.avbaserver, bdspath)
            except Exception as unexport_bds_e:
                logging.error(unexport_bds_e)
                pass
            try:
                sync_buffers()
            except Exception as sync_buffers_e:
                logging.error(sync_buffers_e)
                pass
            try:
                unmnt_removeable(args.backupdisk)
            except Exception as unmnt_removeable_e:
                logging.error(unmnt_removeable_e)
                pass    

    try:
        unexport_bds(args.avbaserver, bdspath)
    except (OSError, subprocess.CalledProcessError) as e:
        try:
            raise
        finally:
            """If Unexport fails we still attempt cleanup."""
            try:
                sync_buffers()
            except Exception as sync_buffers_e:
                logging.error(sync_buffers_e)
                pass
            try:
                unmnt_removeable(args.backupdisk)
            except Exception as unmnt_removeable_e:
                logging.error(unmnt_removeable_e)
                pass    

    try:
        sync_buffers()
    except Exception as e:
        logging.error(e)
        pass

    try:
        unmnt_removeable(args.backupdisk)
    except (OSError, subprocess.CalledProcessError) as e:
        raise

    if not result:
        raise Exception('Warning encountered during stop process!')
    return


def body_creator(log_file):
    body = []
    for line in open(log_file):
        body.append(line)
    return ''.join(body)


def relay_email(smtpserver, smtprecipient, smtpsender, smtpsubject, body):
    message = Message(From=smtpsender, To=smtprecipient, Subject=smtpsubject)
    message.Body = body
    sender = Mailer(smtpserver)
    sender.send(message)

  
def main():

    log_file = '/var/log/bdsrotator.log'

    """Setup argparse."""
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    """Positional arguments."""
    parser.add_argument('viserver',
        help='vCenter or ESX(i) hostname or IP')

    parser.add_argument('avbaserver',
        help='PHD Archive VBA hostname or IP')

    parser.add_argument('avbaname',
        help='PHD Archive VBA name in vSphere')

    parser.add_argument('process', choices=['start', 'stop'],
        help='Start: Mount and export removeable disk then boot Archive VBA | Stop: Shutdown Archive VBA, unexport removeable disk and unmount it')

    """Optional arguments."""
    parser.add_argument('-u', '--username',
        help='vCenter or ESX(i) username',
        default=None)

    parser.add_argument('-p', '--password',
        help='vCenter or ESX(i) password',
        default=None)

    parser.add_argument('-d', '--backupdisk',
        help='Backup disk mount point',
        default='/mnt/backup')

    parser.add_argument('-n', '--netrcfile',
        help='Specify location of netrc file',
        default='~/.netrc')

    parser.add_argument('-b', '--bdsdir',
        help='BDS directory on root of backupdisk',
        default='VBABACKUPS')

    parser.add_argument('-l', '--log-level',
        help='set logging level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])

    whoatnode = getpass.getuser() + '@' + platform.node()
    parser.add_argument('-e', '--smtpsender',
        help='Sender email address',
        default=whoatnode)

    who = getpass.getuser()
    parser.add_argument('-r', '--smtprecipient',
        help='Recipient email address',
        default=who)

    parser.add_argument('-t', '--smtpserver',
        help='SMTP server address',
        default='localhost')

    host = platform.node()
    parser.add_argument('-s', '--smtpsubject',
        help='Email Subject',
        default='bdsrotator on %s encountered an error' %(host))

    parser.add_argument('-f', '--nfsopts',
        help='nfs export options',
        default='rw,no_root_squash,async,no_subtree_check')

    """Create variables from argparse."""
    args = parser.parse_args()

    logging.basicConfig(
        filename=log_file, format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%F %H:%M:%S', filemode='w',
        level=args.log_level)

    """Agnostically obtain paths for exes."""
    global sync, mount, umount, exportfs, showmount
    ospaths = '/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin'
    sync = find_executable('sync', path=ospaths)
    mount = find_executable('mount', path=ospaths)
    umount = find_executable('umount', path=ospaths)
    exportfs = find_executable('exportfs', path=ospaths)
    showmount = find_executable('showmount', path=ospaths)
    try:
        if not exportfs:
            raise FindExeError('exportfs executable not found, is it installed?')
        if not showmount:
            raise FindExeError('showmount executable not found, is it installed?')
        if not sync:
            raise FindExeError('sync executable not found.')
        if not mount:
            raise FindExeError('mount executable not found.')
        if not umount:
            raise FindExeError('umount executable not found.')
    except FindExeError as e:
        logging.error(e)
        traceback.print_exc()
        return 1
    

    if args.process == 'start':
        logging.info('Process Action: start')
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
                traceback.print_exc()
                return 1

    if args.process == 'stop':
        logging.info('Process Action: stop')
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
                traceback.print_exc()
                return 1


if __name__ == '__main__':
    sys.exit(main())

