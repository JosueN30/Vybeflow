"""Create sim users dynamically using PRAGMA table_info."""
import sqlite3
from werkzeug.security import generate_password_hash

DB = r'd:\Vybeflow-main\instance\vybeflow.db'

BASE_DEFAULTS = {
    'adult_verified': 0, 'adult_access_revoked': 0, 'is_admin': 0,
    'default_visibility': 'public', 'ai_assist': 0, 'retro_2011': 0,
    'safe_mode': 0, 'email_notifications': 0, 'live_collab': 0, 'auto_captions': 0,
    'profile_visibility': 'public', 'follow_approval': 0, 'show_activity_status': 1,
    'who_can_message': 'everyone', 'message_credits': 100, 'who_can_comment': 'everyone',
    'who_can_tag': 'everyone', 'read_receipts': 1, 'allow_story_sharing': 1,
    'story_replies': 'everyone', 'allow_reel_remix': 1, 'allow_reel_download': 1,
    'hide_like_counts': 0, 'restrict_unknown': 0, 'two_factor': 0, 'login_alerts': 1,
    'login_attempts': 0, 'is_venue': 0, 'is_promoter': 0, 'account_type': 'regular',
    'professional_verified': 0, 'is_shadow_banned': 0, 'dm_bypass_attempts': 0,
    'dm_strikes': 0, 'violation_count': 0, 'negativity_warnings': 0, 'is_suspended': 0,
    'appeal_pending': 0, 'fake_account_warnings': 0, 'is_banned': 0, 'email_verified': 0,
    'trust_score': 100, 'is_verified_human': 1, 'message_filter_level': 'standard',
    'scam_flags': 0, 'energy_filter_enabled': 1, 'anonymous_posting_enabled': 0,
    'is_burn_account': 0, 'hidden_profile': 0, 'wallpaper_type': 'solid',
    'feed_mode': 'vybeflow', 'wallpaper_color1': '#ff993a', 'wallpaper_color2': '#0a0008',
    'wallpaper_pattern': 'dots', 'wallpaper_animation': 0, 'wallpaper_motion': 0,
    'wallpaper_glitter': 0, 'wallpaper_music_sync': 0, 'inbox_mode': 'all',
    'message_fee': 0, 'home_currency': 'USD', 'currency_code': 'USD',
    'wallet_balance': 0.0, 'dm_fee_multiplier': 1.0, 'is_new_user': 1,
    'has_completed_onboarding': 0, 'wellbeing_break_reminder': 0, 'post_streak': 0,
    'created_at': '2026-04-28 00:00:00', 'updated_at': '2026-04-28 00:00:00',
}

conn = sqlite3.connect(DB)
c = conn.cursor()
conn.execute('PRAGMA foreign_keys=OFF')
c.execute("DELETE FROM user WHERE username IN ('alice_vybe','bob_vybe')")

col_info = c.execute('PRAGMA table_info(user)').fetchall()
# col_info rows: (cid, name, type, notnull, dflt_value, pk)

def insert_user(username, email, password, display_name):
    pw = generate_password_hash(password)
    identity = {'username': username, 'email': email, 'password_hash': pw, 'display_name': display_name}
    fields = []
    vals = []
    for row in col_info:
        name = row[1]
        notnull = row[3]
        dflt = row[4]
        pk = row[5]
        if pk:  # skip primary key (autoincrement)
            continue
        if name in identity:
            fields.append(name)
            vals.append(identity[name])
        elif name in BASE_DEFAULTS:
            fields.append(name)
            vals.append(BASE_DEFAULTS[name])
        elif notnull and dflt is None:
            # Must provide a value — guess from name
            n = name.lower()
            if any(x in n for x in ['count','score','attempts','flags','credits','balance','streak','fee','multiplier','warnings','strikes']):
                fields.append(name); vals.append(0)
            elif any(n.startswith(p) for p in ['is_','has_','allow','show_','hide_','two_','read_','energy_','anonymous_','wellbeing_']):
                fields.append(name); vals.append(0)
            elif any(x in n for x in ['mode','type','visibility','currency','code','_at']):
                fields.append(name); vals.append('default')
            else:
                fields.append(name); vals.append(0)
        # else: nullable or has default — skip, SQLite will use default
    sql = 'INSERT INTO user ({}) VALUES ({})'.format(','.join(fields), ','.join('?'*len(fields)))
    c.execute(sql, vals)
    return c.lastrowid

alice_id = insert_user('alice_vybe', 'alice@sim.local', 'Alice@Secure1!', 'Alice Vybe')
bob_id   = insert_user('bob_vybe',   'bob@sim.local',   'Bob@Secure1!',   'Bob Vybe')
conn.commit()
conn.execute('PRAGMA foreign_keys=ON')
conn.close()
print('Created alice_vybe (id={}) and bob_vybe (id={})'.format(alice_id, bob_id))
