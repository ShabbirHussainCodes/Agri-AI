-- ADR-0014: crop scope. Which crops a document is a curated SOURCE for.
--
-- Written by the laptop ingest job from ingest/sources.yaml (`crops_covered`,
-- one human decision per document, with its reason next to it -- the same
-- review discipline as ADR-0012). Read by /ask: a question that names a crop
-- may only be answered from passages of documents that cover that crop
-- (app/safety/crop_scope.py).
--
-- Keys are the canonical crop keys of app/safety/crop_scope.CROP_LEXICON
-- ('tomato', 'eggplant', ...), not public.crops ids: the corpus covers
-- kitchen-garden vegetables that public.crops (the farm-onboarding list)
-- does not have, and a document is a source for several crops at once.
-- tests/test_crop_scope.py checks every key in sources.yaml is known.
--
-- The default is the empty list on purpose: a document nobody has reviewed
-- covers no crop, so it can never answer a crop-specific question (fail
-- closed). Questions that name no crop are unaffected.

alter table public.documents
  add column crops_covered text[] not null default '{}';

comment on column public.documents.crops_covered is
  'ADR-0014: canonical crop keys this document is a curated source for. Empty = covers no crop.';
