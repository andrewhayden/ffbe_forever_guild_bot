"""Module containing reminders functionality for the guild bot."""
import datetime
from typing import Dict, List
from pytz import utc
import apscheduler
import apscheduler.triggers.date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

class Reminders:
    """Reminders functionality for the guild bot"""
    def __init__(self, reminders_database_path: str):
        self.reminders_database_path = reminders_database_path
        self.scheduler : AsyncIOScheduler = None

    def start(self, event_loop):
        """Start the reminder service."""
        self.scheduler = AsyncIOScheduler(event_loop=event_loop)
        self.scheduler.add_jobstore(SQLAlchemyJobStore(url='sqlite:///' + self.reminders_database_path))
        self.scheduler.start()

    def stop(self):
        """Stop the reminder service immediately."""
        self.scheduler.shutdown(wait=False)
        del self.scheduler

    def addWhimsyReminder(self, owner_name: str, owner_id: str, nrg_reminder_callback: callable, nrg_reminder_args: List[str], spawn_reminder_callback: callable,
        spawn_reminder_args: List[str], nrg_time_ms_override: int = None, spawn_time_ms_override: int = None):
        """Add a whimsy shop reminder. Actually a pair of reminders, one for NRG spending and one for whimsy spawning.

        The first reminder is set for 30 minutes after now, and reminds the user that they can now start spending NRG.
        The second reminder is set for 60 minutes after now, and reminds the user that they can now spawn a new Whimsy shop.

        args:
        owner_name                  name of the owner, used in the description of the task.
        ower_id                     unique ID of the owner, used to construct IDs for the reminders.
        nrg_reminder_callback       the callback function (must be a callable) to be invoked for the nrg reminder.
        nrg_reminder_args           positional arguments to be passed to the nrg_reminder_callback.
        spawn_reminder_callback     the callback function (must be a callable) to be invoked for the whimsy spawn reminder.
        spawn_reminder_args         positional arguments to be passed to the spawn_reminder_callback.
        nrg_time_ms_override        if specified, overrides the amount of time before the nrg reminder fires from 30 minutes to the specified number of ms
        spawn_time_ms_override      if specified, overrides the amount of time before the spawn reminder fires from 60 minutes to the specified number of ms

        The nrg reminder will have the name "<owner_name>#whimsy-nrg", i.e. if the owner_name is "bob" then the ID of the reminder is "bob#whimsy-nrg"
        The spawn reminder will have the name "<owner_name>#whimsy-spawn", i.e. if the owner_name is "bob" then the ID of the reminder is "bob#whimsy-spawn"
        """
        nrg_job_id = owner_id + '#whimsy-nrg'
        nrg_job_desc = '#whimsy-nrg reminder for ' + owner_name + ' (id=' + owner_name + ')'
        now = datetime.datetime.now(tz=utc)
        nrg_execute_at = now + datetime.timedelta(minutes=30)
        if nrg_time_ms_override:
            nrg_execute_at = now + datetime.timedelta(milliseconds=nrg_time_ms_override)
        spawn_job_id = owner_id + '#whimsy-spawn'
        spawn_job_desc = '#whimsy-spawn reminder for ' + owner_name + ' (id=' + owner_name + ')'
        spawn_execute_at = now + datetime.timedelta(hours=1)
        if spawn_time_ms_override:
            spawn_execute_at = now + datetime.timedelta(milliseconds=spawn_time_ms_override)
        self.scheduler.add_job(nrg_reminder_callback, trigger='date', run_date=nrg_execute_at, args=nrg_reminder_args, kwargs=None,
            id=nrg_job_id, name=nrg_job_desc, misfire_grace_time=30*60, coalesce=True, max_instances=1, replace_existing=True)
        self.scheduler.add_job(spawn_reminder_callback, trigger='date', run_date=spawn_execute_at, args=spawn_reminder_args, kwargs=None,
            id=spawn_job_id, name=spawn_job_desc, misfire_grace_time=30*60, coalesce=True, max_instances=1, replace_existing=True)

    def getWhimsyReminders(self, owner_id: str) -> Dict[str, apscheduler.job.Job]:
        """Fetch any whimsy reminders outstanding for the specified owner id.

        The returned dictionary contains 2 entries:
            'nrg':  <the NRG reminder, or None if there is no such reminder or the reminder has expired.>
            'spawn': <the spawn reminder, or None if there is no such reminder or the reminder has expired.>
        """
        return {
            'nrg': self.scheduler.get_job(owner_id + '#whimsy-nrg'),
            'spawn': self.scheduler.get_job(owner_id + '#whimsy-spawn'),
        }

    def hasPendingWhimsyNrgReminder(self, owner_id: str) -> bool:
        """Return true if the specified user has a pending whimsy shop NRG reminder."""
        scheduled: Dict[str, apscheduler.job.Job] = self.getWhimsyReminders(owner_id)
        return scheduled and 'nrg' in scheduled and scheduled['nrg'] and scheduled['nrg'].next_run_time and scheduled['nrg'].next_run_time > datetime.datetime.now(tz=utc)

    def hasPendingWhimsySpawnReminder(self, owner_id: str) -> bool:
        """Return true if the specified user has a pending whimsy shop spawn reminder."""
        scheduled: Dict[str, apscheduler.job.Job] = self.getWhimsyReminders(owner_id)
        return scheduled and 'spawn' in scheduled and scheduled['spawn'] and scheduled['spawn'].next_run_time and scheduled['spawn'].next_run_time > datetime.datetime.now(tz=utc)

    def timeTillWhimsyNrgReminder(self, owner_id: str) -> int:
        """If the specified user has a whimsy-shop NRG reminder in the future, return the number of seconds until that reminder fires; else return None."""
        scheduled: Dict[str, apscheduler.job.Job] = self.getWhimsyReminders(owner_id)
        if scheduled and 'nrg' in scheduled and scheduled['nrg'] and scheduled['nrg'].next_run_time and scheduled['nrg'].next_run_time > datetime.datetime.now(tz=utc):
            next_run_time: datetime.datetime = scheduled['nrg'].next_run_time
            return (next_run_time - datetime.datetime.now(tz=utc)).total_seconds()
        return None

    def timeTillWhimsySpawnReminder(self, owner_id: str) -> int:
        """If the specified user has a whimsy-shop spawn reminder in the future, return the number of seconds until that reminder fires; else return None."""
        scheduled: Dict[str, apscheduler.job.Job] = self.getWhimsyReminders(owner_id)
        if scheduled and 'spawn' in scheduled and scheduled['spawn'] and scheduled['spawn'].next_run_time and scheduled['spawn'].next_run_time > datetime.datetime.now(tz=utc):
            next_run_time: datetime.datetime = scheduled['spawn'].next_run_time
            return (next_run_time - datetime.datetime.now(tz=utc)).total_seconds()
        return None

    def cancelWhimsyReminders(self, owner_id: str):
        """Cancels any and all oustanding whimsy reminders for the specified owner."""
        job: apscheduler.job.Job = None
        job = self.scheduler.get_job(owner_id + '#whimsy-nrg')
        if job:
            job.remove()
        job = self.scheduler.get_job(owner_id + '#whimsy-spawn')
        if job:
            job.remove()