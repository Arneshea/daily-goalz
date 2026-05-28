# DayGoalz 🎯

A brutalist habit tracker with monthly/weekly grids, stats, history, and multi-user support.

---

## Stack
- **Backend**: Flask (Python)
- **Database**: Supabase (PostgreSQL)
- **Frontend**: Tailwind CSS + vanilla JS (no build step)
- **Deploy**: Vercel + GitHub

---

## 1. Supabase Setup

1. Create a free account at https://supabase.com
2. Create a new project
3. Go to **SQL Editor** in the left sidebar
4. Paste and run this SQL:

```sql
create table users (
  id uuid primary key default gen_random_uuid(),
  username text unique not null,
  email text unique not null,
  password_hash text not null,
  created_at timestamptz default now()
);

create table goals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade not null,
  name text not null,
  emoji text default '🎯',
  category text default 'General',
  frequency text default 'daily',
  created_at timestamptz default now()
);

create table checks (
  id uuid primary key default gen_random_uuid(),
  goal_id uuid references goals(id) on delete cascade not null,
  checked_date date not null,
  unique(goal_id, checked_date)
);

-- Indexes for performance
create index on goals(user_id);
create index on checks(goal_id);
create index on checks(checked_date);
```

5. Go to **Settings → Database → Connection string** and copy the **URI** (starts with `postgresql://`)

---

## 2. Local Development

```bash
# Clone / cd into the project
cd daygoalz

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env and fill in DATABASE_URL and SECRET_KEY

# Run locally
python api/index.py
# Visit http://localhost:5000
```

---

## 3. Deploy to Vercel via GitHub

1. Push the project to a GitHub repository
2. Go to https://vercel.com → **New Project** → import your repo
3. In Vercel project settings → **Environment Variables**, add:
   - `DATABASE_URL` — your Supabase connection string
   - `SECRET_KEY`   — a long random string
4. Click **Deploy** — done!

Every `git push` to main auto-deploys.

---

## File Structure

```
daygoalz/
├── api/
│   └── index.py          ← Flask app (all routes, auth, API)
├── static/
│   ├── css/style.css     ← Custom styles on top of Tailwind
│   └── js/utils.js       ← Shared JS helpers
├── templates/
│   ├── base.html         ← Layout, nav, modal
│   ├── login.html
│   ├── register.html
│   ├── monthly.html      ← Monthly grid view
│   ├── weekly.html       ← Weekly card view
│   ├── stats.html        ← Analytics dashboard
│   └── history.html      ← Past months archive
├── requirements.txt
├── vercel.json
├── .env.example
└── README.md
```

---

## Features

- Register / login (bcrypt passwords, server-side sessions)
- Add, edit, delete goals with emoji + category + frequency
- Monthly grid — tick off each day, future days locked
- Weekly view — 7-day card layout, navigate weeks
- Stats — completion %, streak, bar chart, heatmap, per-goal bars
- History — last 6 months with expandable goal breakdowns
- Theme switcher (earthy → dark → ocean → lavender)
- Fully private per-user data
