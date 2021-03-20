"""Module containing reminders functionality for the guild bot."""
import datetime
from typing import Dict, List
from pytz import utc
import apscheduler
import apscheduler.triggers.date
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

class Reminders:
    """Reminders functionality for the guild bot"""
    def __init__(self, reminders_database_path: str):
        self.reminders_database_path = reminders_database_path
        self.scheduler : BackgroundScheduler = None

    def start(self):
        """Start the reminder service."""
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_jobstore(SQLAlchemyJobStore(url='sqlite:///' + self.reminders_database_path))
        self.scheduler.start()

    def stop(self):
        """Stop the reminder service immediately."""
        self.scheduler.shutdown(wait=False)
        del self.scheduler

    def addWhimsyReminder(self, owner_name: str, nrg_reminder_callback: callable, nrg_reminder_args: List[str], spawn_reminder_callback: callable,
        spawn_reminder_args: List[str], nrg_time_ms_override: int = None, spawn_time_ms_override: int = None):
        """Add a whimsy shop reminder. Actually a pair of reminders, one for NRG spending and one for whimsy spawning.

        The first reminder is set for 30 minutes after now, and reminds the user that they can now start spending NRG.
        The second reminder is set for 60 minutes after now, and reminds the user that they can now spawn a new Whimsy shop.

        args:
        owner_name                  name of the owner, used to construct IDs for the reminders.
        nrg_reminder_callback       the callback function (must be a callable) to be invoked for the nrg reminder.
        nrg_reminder_args           positional arguments to be passed to the nrg_reminder_callback.
        spawn_reminder_callback     the callback function (must be a callable) to be invoked for the whimsy spawn reminder.
        spawn_reminder_args         positional arguments to be passed to the spawn_reminder_callback.
        nrg_time_ms_override        if specified, overrides the amount of time before the nrg reminder fires from 30 minutes to the specified number of ms
        spawn_time_ms_override      if specified, overrides the amount of time before the spawn reminder fires from 60 minutes to the specified number of ms

        The nrg reminder will have the name "<owner_name>#whimsy-nrg", i.e. if the owner_name is "bob" then the ID of the reminder is "bob#whimsy-nrg"
        The spawn reminder will have the name "<owner_name>#whimsy-spawn", i.e. if the owner_name is "bob" then the ID of the reminder is "bob#whimsy-spawn"
        """
        nrg_job_id = owner_name + '#whimsy-nrg'
        now = datetime.datetime.now(tz=utc)
        nrg_execute_at = now + datetime.timedelta(minutes=30)
        if nrg_time_ms_override:
            nrg_execute_at = now + datetime.timedelta(milliseconds=nrg_time_ms_override)
        spawn_job_id = owner_name + '#whimsy-spawn'
        spawn_execute_at = now + datetime.timedelta(hours=1)
        if spawn_time_ms_override:
            spawn_execute_at = now + datetime.timedelta(milliseconds=spawn_time_ms_override)
        self.scheduler.add_job(nrg_reminder_callback, trigger='date', run_date=nrg_execute_at, args=nrg_reminder_args, kwargs=None,
            id=nrg_job_id, name=nrg_job_id, misfire_grace_time=30*60, coalesce=True, max_instances=1, replace_existing=True)
        self.scheduler.add_job(spawn_reminder_callback, trigger='date', run_date=spawn_execute_at, args=spawn_reminder_args, kwargs=None,
            id=spawn_job_id, name=spawn_job_id, misfire_grace_time=30*60, coalesce=True, max_instances=1, replace_existing=True)

    def getWhimsyReminders(self, owner_name) -> Dict[str, apscheduler.job.Job]:
        """Fetch any whimsy reminders outstanding for the specified owner.

        The returned dictionary contains 2 entries:
            'nrg':  <the NRG reminder, or None if there is no such reminder or the reminder has expired.>
            'spawn': <the spawn reminder, or None if there is no such reminder or the reminder has expired.>
        """
        return {
            'nrg': self.scheduler.get_job(owner_name + '#whimsy-nrg'),
            'spawn': self.scheduler.get_job(owner_name + '#whimsy-spawn'),
        }
