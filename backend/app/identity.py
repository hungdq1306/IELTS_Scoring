"""Display-only profile cache, sourced exclusively from verified identity providers."""
import time
import httpx
from urllib.parse import quote

def display_label(user):
    return user.full_name or user.reported_full_name or user.email or user.reported_email or 'User #' + user.id[:8]

def profile_fields(claims):
    fields = {}
    for key, limit, value in [('full_name',200,claims.get('full_name') or claims.get('name')),
                              ('email',320,claims.get('email') or claims.get('email_address')),
                              ('avatar_url',2000,claims.get('picture') or claims.get('image_url'))]:
        if isinstance(value,str) and value.strip() and len(value)<=limit:
            if key=='email' and ('@' not in value or '\n' in value):continue
            if key=='avatar_url' and not value.startswith('https://'):continue
            fields[key]=value.strip()
    return fields

async def clerk_profile(subject, secret):
    if not secret:return {}
    async with httpx.AsyncClient(timeout=5,follow_redirects=False) as client:
        response=await client.get('https://api.clerk.com/v1/users/'+quote(subject,safe=''),headers={'Authorization':'Bearer '+secret})
        response.raise_for_status()
        data=response.json()
    email=next((a.get('email_address') for a in data.get('email_addresses',[]) if a.get('id')==data.get('primary_email_address_id')),None)
    return profile_fields({'full_name':' '.join(filter(None,[data.get('first_name'),data.get('last_name')])) or data.get('username'),
                           'email':email,'image_url':data.get('image_url')})

async def sync_profile(database,user,claims,settings,force=False):
    fields=profile_fields(claims)
    due=force or user.profile_synced_at is None or user.profile_synced_at<time.time()-300
    if due and (force or not fields.get('email') or not fields.get('full_name')):
        try:
            fields={**fields,**await clerk_profile(user.external_auth_id,settings.clerk_secret_key.get_secret_value())}
        except httpx.HTTPError:
            pass  # A profile outage cannot grant roles or deny a valid sign-in.
    fields={key:value for key,value in fields.items() if getattr(user,key)!=value}
    if not fields and not due:return user
    async with database.transaction() as db:
        stored=await db.get(type(user),user.id)
        for key,value in fields.items():setattr(stored,key,value)
        if due:stored.profile_synced_at=time.time()
        await db.flush()
        return stored


def public_profile(user):
    # Browser data is display-only and never overwrites provider-verified values.
    return {'full_name': user.full_name or user.reported_full_name,
            'email': user.email or user.reported_email, 'avatar_url': user.avatar_url,
            'name_source': 'provider' if user.full_name else 'self_reported' if user.reported_full_name else None,
            'email_source': 'provider' if user.email else 'self_reported' if user.reported_email else None,
            'display_label': display_label(user)}
