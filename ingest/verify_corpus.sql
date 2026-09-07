-- Phase 3 corpus verification. Read-only; run after `python run.py`.
-- Prefer verify_corpus.py -- it needs no psql and reports PASS/FAIL.
--   psql postgresql://postgres:postgres@127.0.0.1:54322/postgres -f verify_corpus.sql

\echo '=== 1. documents ==='
select handle, published_year as yr, doc_type, licence, language as lang,
       page_count as pages, left(title, 46) as title
from public.documents order by handle;

\echo ''
\echo '=== 2. chunks per document + metadata coverage ==='
select d.handle,
       count(*)                       as chunks,
       count(c.page_no)               as with_page,
       count(c.section_path)          as with_section,
       count(c.crop_id)               as with_crop,
       min(c.page_no)                 as min_pg,
       max(c.page_no)                 as max_pg
from public.chunks c
join public.documents d on d.id = c.document_id
group by d.handle
order by d.handle;

\echo ''
\echo '=== 3. EXCLUSION CHECK -- pages 11-13 of 10568/180614 must return ZERO rows ==='
select d.handle, c.page_no, count(*) as leaked_chunks
from public.chunks c
join public.documents d on d.id = c.document_id
where d.handle = '10568/180614' and c.page_no in (11, 12, 13)
group by d.handle, c.page_no;

\echo ''
\echo '=== 4. embeddings and lexical index ==='
-- Dimension is enforced by the column type vector(384), so a wrong-sized
-- vector could not have been inserted. verify_corpus.py additionally samples
-- vectors and checks their L2 norm in Python.
select count(*)                                        as total_chunks,
       count(embedding)                                as with_embedding,
       count(*) filter (where tsv is not null)         as with_tsv,
       count(*) filter (where tsv = ''::tsvector)      as empty_tsv
from public.chunks;

\echo ''
\echo '=== 5. crop_id resolution (Tomato expected only on the tomato article) ==='
select d.handle, coalesce(cr.name_en, '(none)') as crop, count(*) as chunks
from public.chunks c
join public.documents d on d.id = c.document_id
left join public.crops cr on cr.id = c.crop_id
group by d.handle, cr.name_en
order by d.handle, crop;

\echo ''
\echo '=== 6. state metadata ==='
select coalesce(state, '(none)') as state, count(*) from public.chunks group by 1 order by 2 desc;

\echo ''
\echo '=== 7. three sample chunks ==='
select page_no, left(coalesce(section_path,'(none)'), 30) as section,
       token_count as tok, left(content, 90) as content
from public.chunks order by random() limit 3;
