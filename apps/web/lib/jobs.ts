// Wait for a generation job to finish via Supabase Realtime (ARCHITECTURE §5),
// instead of polling. RLS restricts the generation_jobs row to household members,
// and Realtime honors it, so we only receive our own job's changes.

import { api, type JobStatus } from "./api";
import { supabase } from "./supabase";

type JobRow = {
  status: JobStatus["status"];
  result: JobStatus["result"];
  error: string | null;
};

/** Resolves when the job reaches `done`; rejects on `failed`. `onStatus` fires on
 *  each transition for progress display. */
export async function waitForJob(
  jobId: string,
  onStatus?: (status: string) => void,
): Promise<JobStatus> {
  // Make sure the Realtime socket is authenticated so RLS lets the row through.
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (token) await supabase.realtime.setAuth(token);

  return new Promise<JobStatus>((resolve, reject) => {
    let settled = false;
    const channel = supabase.channel(`job-${jobId}`);

    const finish = (job: JobStatus) => {
      if (settled) return;
      settled = true;
      void supabase.removeChannel(channel);
      if (job.status === "failed") reject(new Error(job.error ?? "generation failed"));
      else resolve(job);
    };

    channel
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "public",
          table: "generation_jobs",
          filter: `id=eq.${jobId}`,
        },
        (payload) => {
          const row = payload.new as JobRow;
          onStatus?.(row.status);
          if (row.status === "done" || row.status === "failed") {
            finish({ id: jobId, kind: "meal_plan", ...row });
          }
        },
      )
      .subscribe(async (status) => {
        // The job may have finished before the subscription went live — catch up.
        if (status === "SUBSCRIBED") {
          const job = await api.getJob(jobId);
          onStatus?.(job.status);
          if (job.status === "done" || job.status === "failed") finish(job);
        }
      });
  });
}
