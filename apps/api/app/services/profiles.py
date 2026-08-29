"""Profile provisioning. There is no dedicated "create account" endpoint —
a farmer's `profiles` row is created lazily, the first time they do any
authenticated action, from their JWT's own claims. See checkpoint 5 notes
in the chat history / commit message for why.
"""
import asyncpg

from app.core.auth import AuthContext


async def ensure_profile(conn: asyncpg.Connection, user: AuthContext) -> None:
    email = user.claims.get("email")
    await conn.execute(
        """
        insert into public.profiles (id, display_name)
        values ($1, $2)
        on conflict (id) do nothing
        """,
        user.user_id,
        email,
    )
