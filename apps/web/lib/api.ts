import { API_BASE } from "./config";

/** One error shape for every way the API can fail. The API answers with
 *  {error:{code,message,scope?}} for its own errors and {detail} for FastAPI's
 *  (401 from auth, 422 validation), so both are normalised here. */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
    public scope?: string,
  ) {
    super(message);
  }
}

type Options = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  /** A multipart upload (a photo). The browser sets the Content-Type with its boundary; it must not be set by hand. */
  form?: FormData;
  token: string;
};

export async function api<T>(path: string, { method = "GET", body, form, token }: Options): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body === undefined || form ? {} : { "Content-Type": "application/json" }),
      },
      body: form ?? (body === undefined ? undefined : JSON.stringify(body)),
    });
  } catch {
    // Offline, the server is asleep, or CORS refused it: the farmer needs one clear message.
    throw new ApiError(0, "network", "network");
  }
  if (res.status === 204) return undefined as T;
  if (res.ok) return (await res.json()) as T;

  let message = res.statusText;
  let code: string | undefined;
  let scope: string | undefined;
  try {
    const data = await res.json();
    if (data?.error) {
      message = data.error.message ?? message;
      code = data.error.code;
      scope = data.error.scope;
    } else if (typeof data?.detail === "string") {
      message = data.detail;
    } else if (Array.isArray(data?.detail)) {
      code = "invalid_input";
      message = "invalid input";
    }
  } catch {
    /* body was not JSON */
  }
  throw new ApiError(res.status, message, code, scope);
}
