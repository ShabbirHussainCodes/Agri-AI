"use client";

import { useEffect, useState } from "react";
import { supabase } from "./supabase";

const BUCKET = "crop-photos";

/** A short-lived link to a stored scan photo. The bucket is private: the link is made with the farmer's own
 *  session, so storage's row-level policy decides whether it works (apps/api migration 20261010120000).
 *  Any failure just means no thumbnail. */
export function useSignedPhoto(path: string | null | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    if (!path) return;
    supabase()
      .storage.from(BUCKET)
      .createSignedUrl(path, 3600)
      .then(({ data }) => {
        if (!cancelled) setUrl(data?.signedUrl ?? null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [path]);
  return path ? url : null;
}
