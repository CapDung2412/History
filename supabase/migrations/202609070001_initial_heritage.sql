begin;

create extension if not exists pgcrypto;

create table if not exists public.heritage_items (
    id text primary key check (id ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    slug text not null unique check (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    name text not null check (length(btrim(name)) > 0),
    category text not null check (length(btrim(category)) > 0),
    dataset_name text not null,
    dataset_version text not null,
    address text,
    city text,
    province text,
    country text,
    latitude double precision check (latitude between -90 and 90),
    longitude double precision check (longitude between -180 and 180),
    published boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.heritage_stories (
    item_id text primary key references public.heritage_items(id) on delete cascade,
    title text not null check (length(btrim(title)) > 0),
    description text not null check (length(btrim(description)) > 0),
    historical_period text,
    historical_year integer check (historical_year between -5000 and 3000),
    event_name text,
    source_text text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.heritage_images (
    id text primary key,
    item_id text not null references public.heritage_items(id) on delete cascade,
    filename text not null check (
        length(btrim(filename)) > 0
        and filename !~ '[\\/]'
        and filename not in ('.', '..')
    ),
    relative_path text not null check (
        length(btrim(relative_path)) > 0
        and relative_path !~ '(^/|\\|(^|/)\.\.(/|$))'
    ),
    drive_url text,
    caption text not null check (length(btrim(caption)) > 0),
    image_year integer check (image_year between -5000 and 3000),
    view_name text,
    sort_order integer not null default 0 check (sort_order >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (item_id, filename),
    unique (item_id, sort_order)
);

create table if not exists public.heritage_sources (
    id text primary key,
    item_id text not null references public.heritage_items(id) on delete cascade,
    citation text not null check (length(btrim(citation)) > 0),
    title text,
    url text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (item_id, citation)
);

create table if not exists public.heritage_tags (
    -- Canonical JSON tags include both hyphenated slugs and category values with underscores.
    slug text primary key check (slug ~ '^[a-z0-9]+(?:[-_][a-z0-9]+)*$'),
    label text not null check (length(btrim(label)) > 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.heritage_item_tags (
    item_id text not null references public.heritage_items(id) on delete cascade,
    tag_slug text not null references public.heritage_tags(slug) on delete cascade,
    primary key (item_id, tag_slug)
);

create table if not exists public.heritage_challenges (
    id text primary key,
    item_id text not null references public.heritage_items(id) on delete cascade,
    question_type text not null check (
        question_type in ('single_choice', 'true_false', 'period_choice', 'category_choice')
    ),
    question text not null check (length(btrim(question)) > 0),
    explanation text not null check (length(btrim(explanation)) > 0),
    source_field text not null check (source_field in ('title', 'historical_year', 'historical_period', 'category')),
    published boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (item_id, source_field)
);

create table if not exists public.heritage_challenge_options (
    id text primary key,
    challenge_id text not null references public.heritage_challenges(id) on delete cascade,
    label text not null check (length(btrim(label)) > 0),
    is_correct boolean not null default false,
    sort_order integer not null default 0 check (sort_order >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (challenge_id, sort_order)
);

create table if not exists public.recognition_requests (
    request_id uuid primary key,
    created_at timestamptz not null default now(),
    status text not null check (status in ('accepted', 'needs_confirmation', 'rejected', 'error')),
    top1_score double precision check (top1_score between -1 and 1),
    score_margin double precision check (score_margin between 0 and 2),
    resolved_item_id text references public.heritage_items(id) on delete set null,
    candidate_ids text[] not null default '{}',
    quality_issues text[] not null default '{}',
    quality_metrics jsonb not null default '{}'::jsonb,
    duration_ms double precision check (duration_ms is null or duration_ms >= 0),
    component_timings_ms jsonb not null default '{}'::jsonb,
    check (status <> 'accepted' or resolved_item_id is not null),
    check (resolved_item_id is null or resolved_item_id = any(candidate_ids))
);

create table if not exists public.recognition_feedback (
    id uuid primary key default gen_random_uuid(),
    request_id uuid not null unique references public.recognition_requests(request_id) on delete cascade,
    created_at timestamptz not null default now(),
    is_correct boolean not null,
    selected_item_id text references public.heritage_items(id) on delete set null,
    no_match boolean not null default false,
    check (not (is_correct and no_match)),
    check (
        (no_match and selected_item_id is null)
        or (not no_match and selected_item_id is not null)
    )
);

create table if not exists public.anonymous_analytics_events (
    id uuid primary key default gen_random_uuid(),
    request_id uuid references public.recognition_requests(request_id) on delete set null,
    event_type text not null check (event_type in (
        'recognition_started', 'recognition_completed', 'recognition_failed',
        'artifact_opened', 'challenge_answered'
    )),
    event_data jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists heritage_items_category_idx
    on public.heritage_items(category) where published;
create index if not exists heritage_items_name_idx on public.heritage_items(name);
create index if not exists heritage_images_item_idx
    on public.heritage_images(item_id, sort_order);
create index if not exists heritage_sources_item_idx on public.heritage_sources(item_id);
create index if not exists heritage_item_tags_tag_idx on public.heritage_item_tags(tag_slug);
create index if not exists heritage_challenges_item_idx
    on public.heritage_challenges(item_id) where published;
create index if not exists recognition_requests_created_idx
    on public.recognition_requests(created_at desc);
create index if not exists recognition_feedback_created_idx
    on public.recognition_feedback(created_at desc);
create index if not exists anonymous_analytics_created_idx
    on public.anonymous_analytics_events(created_at desc);
create index if not exists anonymous_analytics_type_idx
    on public.anonymous_analytics_events(event_type, created_at desc);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists heritage_items_set_updated_at on public.heritage_items;
create trigger heritage_items_set_updated_at
before update on public.heritage_items
for each row execute function public.set_updated_at();

drop trigger if exists heritage_stories_set_updated_at on public.heritage_stories;
create trigger heritage_stories_set_updated_at
before update on public.heritage_stories
for each row execute function public.set_updated_at();

drop trigger if exists heritage_images_set_updated_at on public.heritage_images;
create trigger heritage_images_set_updated_at
before update on public.heritage_images
for each row execute function public.set_updated_at();

drop trigger if exists heritage_sources_set_updated_at on public.heritage_sources;
create trigger heritage_sources_set_updated_at
before update on public.heritage_sources
for each row execute function public.set_updated_at();

drop trigger if exists heritage_tags_set_updated_at on public.heritage_tags;
create trigger heritage_tags_set_updated_at
before update on public.heritage_tags
for each row execute function public.set_updated_at();

drop trigger if exists heritage_challenges_set_updated_at on public.heritage_challenges;
create trigger heritage_challenges_set_updated_at
before update on public.heritage_challenges
for each row execute function public.set_updated_at();

drop trigger if exists heritage_challenge_options_set_updated_at on public.heritage_challenge_options;
create trigger heritage_challenge_options_set_updated_at
before update on public.heritage_challenge_options
for each row execute function public.set_updated_at();

create or replace function public.validate_recognition_feedback()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
    offered_ids text[];
    resolved_id text;
    expected_correct_id text;
begin
    select candidate_ids, resolved_item_id
      into offered_ids, resolved_id
      from public.recognition_requests
     where request_id = new.request_id;

    if not found then
        raise exception 'Unknown recognition request';
    end if;

    expected_correct_id := coalesce(resolved_id, offered_ids[1]);
    if new.is_correct then
        if new.no_match or expected_correct_id is null then
            raise exception 'Correct feedback has no offered result';
        end if;
        if new.selected_item_id is null then
            new.selected_item_id := expected_correct_id;
        elsif new.selected_item_id <> expected_correct_id then
            raise exception 'Correct feedback must refer to the recognized result';
        end if;
    elsif new.no_match then
        if new.selected_item_id is not null then
            raise exception 'No-match feedback cannot select an item';
        end if;
    elsif new.selected_item_id is null then
        raise exception 'Incorrect feedback requires a selected offered result or no-match';
    end if;

    if new.selected_item_id is not null
       and not (new.selected_item_id = any(offered_ids)) then
        raise exception 'Selected item was not offered for this request';
    end if;
    return new;
end;
$$;

drop trigger if exists recognition_feedback_validate on public.recognition_feedback;
create trigger recognition_feedback_validate
before insert or update on public.recognition_feedback
for each row execute function public.validate_recognition_feedback();

alter table public.heritage_items enable row level security;
alter table public.heritage_stories enable row level security;
alter table public.heritage_images enable row level security;
alter table public.heritage_sources enable row level security;
alter table public.heritage_tags enable row level security;
alter table public.heritage_item_tags enable row level security;
alter table public.heritage_challenges enable row level security;
alter table public.heritage_challenge_options enable row level security;
alter table public.recognition_requests enable row level security;
alter table public.recognition_feedback enable row level security;
alter table public.anonymous_analytics_events enable row level security;

drop policy if exists heritage_items_public_read on public.heritage_items;
create policy heritage_items_public_read on public.heritage_items
for select to anon, authenticated using (published);

drop policy if exists heritage_stories_public_read on public.heritage_stories;
create policy heritage_stories_public_read on public.heritage_stories
for select to anon, authenticated using (
    exists (
        select 1 from public.heritage_items item
        where item.id = item_id and item.published
    )
);

drop policy if exists heritage_images_public_read on public.heritage_images;
create policy heritage_images_public_read on public.heritage_images
for select to anon, authenticated using (
    exists (
        select 1 from public.heritage_items item
        where item.id = item_id and item.published
    )
);

drop policy if exists heritage_sources_public_read on public.heritage_sources;
create policy heritage_sources_public_read on public.heritage_sources
for select to anon, authenticated using (
    exists (
        select 1 from public.heritage_items item
        where item.id = item_id and item.published
    )
);

drop policy if exists heritage_tags_public_read on public.heritage_tags;
create policy heritage_tags_public_read on public.heritage_tags
for select to anon, authenticated using (
    exists (
        select 1
          from public.heritage_item_tags link
          join public.heritage_items item on item.id = link.item_id
         where link.tag_slug = slug and item.published
    )
);

drop policy if exists heritage_item_tags_public_read on public.heritage_item_tags;
create policy heritage_item_tags_public_read on public.heritage_item_tags
for select to anon, authenticated using (
    exists (
        select 1 from public.heritage_items item
        where item.id = item_id and item.published
    )
);

revoke insert, update, delete on public.heritage_items from anon, authenticated;
revoke insert, update, delete on public.heritage_stories from anon, authenticated;
revoke insert, update, delete on public.heritage_images from anon, authenticated;
revoke insert, update, delete on public.heritage_sources from anon, authenticated;
revoke insert, update, delete on public.heritage_tags from anon, authenticated;
revoke insert, update, delete on public.heritage_item_tags from anon, authenticated;
revoke all on public.heritage_challenges from anon, authenticated;
revoke all on public.heritage_challenge_options from anon, authenticated;
revoke all on public.recognition_requests from anon, authenticated;
revoke all on public.recognition_feedback from anon, authenticated;
revoke all on public.anonymous_analytics_events from anon, authenticated;

grant select on public.heritage_items to anon, authenticated;
grant select on public.heritage_stories to anon, authenticated;
grant select on public.heritage_images to anon, authenticated;
grant select on public.heritage_sources to anon, authenticated;
grant select on public.heritage_tags to anon, authenticated;
grant select on public.heritage_item_tags to anon, authenticated;

grant all on public.heritage_items to service_role;
grant all on public.heritage_stories to service_role;
grant all on public.heritage_images to service_role;
grant all on public.heritage_sources to service_role;
grant all on public.heritage_tags to service_role;
grant all on public.heritage_item_tags to service_role;
grant all on public.heritage_challenges to service_role;
grant all on public.heritage_challenge_options to service_role;
grant all on public.recognition_requests to service_role;
grant all on public.recognition_feedback to service_role;
grant all on public.anonymous_analytics_events to service_role;

commit;
