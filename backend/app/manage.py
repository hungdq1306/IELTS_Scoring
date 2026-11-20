"""Trusted operator commands; no HTTP route can grant global staff privileges."""
import argparse
import asyncio
import time

from sqlalchemy import delete, func, select

from app.database import Database
from app.models import AuditEvent, Job, Submission, User
from app.pilot_config import PilotSettings
from app.seed import seed_defaults


async def manage(args):
    settings = PilotSettings()
    database = Database(settings.database_url.get_secret_value())
    try:
        if args.command == 'seed':
            await seed_defaults(database)
            print('Default anchors, templates and prompts are ready.')
        elif args.command == 'grant-role':
            async with database.transaction() as session:
                user = await session.scalar(select(User).where(User.external_auth_id == args.clerk_user_id).with_for_update())
                if not user:
                    user = User(external_auth_id=args.clerk_user_id)
                    session.add(user)
                    await session.flush()
                previous = user.role
                user.role = args.role
                session.add(AuditEvent(actor_id=user.id, action='operator_role_grant', target_id=user.id,
                                       detail={'previous': previous, 'role': args.role}))
            print('Role saved. Sign out/in or refresh the account panel.')
        elif args.command == 'purge-expired':
            cutoff = time.time() - settings.retention_days * 86400
            async with database.transaction() as session:
                running = select(Job.submission_id).where(Job.status == 'RUNNING')
                condition = (Submission.created_at < cutoff) & ~Submission.id.in_(running)
                count = await session.scalar(select(func.count()).select_from(Submission).where(condition))
                if args.apply:
                    await session.execute(delete(Submission).where(condition))
            print(f'{count} expired submissions ' + ('deleted.' if args.apply else 'would be deleted; use --apply.'))
        elif args.command == 'set-active':
            async with database.transaction() as session:
                user = await session.scalar(select(User).where(User.external_auth_id == args.clerk_user_id).with_for_update())
                if not user: raise SystemExit('Account not found.')
                user.active = args.active == 'true'
                session.add(AuditEvent(actor_id=user.id, action='operator_account_status', target_id=user.id, detail={'active': user.active}))
            print('Account access status saved.')
        elif args.command == 'delete-writing':
            async with database.transaction() as session:
                user = await session.scalar(select(User).where(User.external_auth_id == args.clerk_user_id).with_for_update())
                if not user:
                    raise SystemExit('Account not found.')
                pending = await session.scalar(select(func.count()).select_from(Job).where(Job.user_id == user.id, Job.status == 'RUNNING'))
                if pending:
                    raise SystemExit('Wait for active jobs to finish or stop the worker before deleting writing.')
                if args.apply:
                    await session.execute(delete(Submission).where(Submission.user_id == user.id))
                    session.add(AuditEvent(actor_id=user.id, action='operator_deleted_writing', target_id=user.id))
            print('Writing deleted.' if args.apply else 'Use --apply to delete this account’s writing; auth account is retained.')
    finally:
        await database.close()


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('seed')
    grant = commands.add_parser('grant-role')
    grant.add_argument('--clerk-user-id', required=True)
    grant.add_argument('--role', choices=['student', 'ta', 'teacher', 'admin'], required=True)
    purge = commands.add_parser('purge-expired')
    purge.add_argument('--apply', action='store_true')
    remove = commands.add_parser('delete-writing')
    remove.add_argument('--clerk-user-id', required=True)
    remove.add_argument('--apply', action='store_true')
    active = commands.add_parser('set-active')
    active.add_argument('--clerk-user-id', required=True)
    active.add_argument('--active', required=True, choices=['true', 'false'])
    asyncio.run(manage(parser.parse_args()))


if __name__ == '__main__':
    main()
