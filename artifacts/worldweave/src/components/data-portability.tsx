import { useMemo, useRef, useState } from 'react';
import {
  useExportUniverse,
  useValidateUniverseImport,
  useExecuteUniverseImport,
  useListImportJobs,
  type ImportValidationResponse,
  type ImportJobResponse,
  type ImportReportItem,
} from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileArchive,
  History,
  Loader2,
  Upload,
} from 'lucide-react';

type ConflictPolicy = 'skip' | 'overwrite' | 'fail';

const ACTION_STYLES: Record<ImportReportItem['action'], string> = {
  create: 'bg-[#e7f1e9] text-[#2f6b45]',
  update: 'bg-[#e8eef5] text-[#33557d]',
  skip: 'bg-[#efece4] text-[#6b6455]',
  conflict: 'bg-[#fbf1dd] text-[#8a6410]',
  error: 'bg-[#fbe9e4] text-[#9b4a36]',
};

function formatCounts(counts: Record<string, Record<string, number>>) {
  return Object.entries(counts)
    .map(([kind, tally]) => {
      const parts = Object.entries(tally)
        .filter(([, value]) => value > 0)
        .map(([action, value]) => `${value} ${action}`);
      return parts.length ? `${kind}: ${parts.join(', ')}` : null;
    })
    .filter(Boolean) as string[];
}

export function DataPortability({
  universeId,
  universeSlug,
  canExport,
  canImport,
}: {
  universeId: string;
  universeSlug: string;
  canExport: boolean;
  canImport: boolean;
}) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validation, setValidation] = useState<ImportValidationResponse | null>(null);
  const [conflictPolicy, setConflictPolicy] = useState<ConflictPolicy>('skip');
  const [lastJob, setLastJob] = useState<ImportJobResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const exportUniverse = useExportUniverse();
  const validateImport = useValidateUniverseImport();
  const executeImport = useExecuteUniverseImport();
  const { data: jobs, refetch: refetchJobs } = useListImportJobs(
    universeId,
    undefined,
    { query: { enabled: canImport } },
  );

  const validationSummary = useMemo(
    () => (validation ? formatCounts(validation.report.counts) : []),
    [validation],
  );

  const resetImport = () => {
    setSelectedFile(null);
    setValidation(null);
    setLastJob(null);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleExport = async () => {
    setError(null);
    try {
      const blob = await exportUniverse.mutateAsync({ universeId });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `worldweave-${universeSlug}-export.zip`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err?.data?.error?.message || 'Export failed.');
    }
  };

  const handleValidate = async (file: File) => {
    setError(null);
    setLastJob(null);
    try {
      const result = await validateImport.mutateAsync({
        universeId,
        data: { file },
      });
      setValidation(result);
    } catch (err: any) {
      setValidation(null);
      setError(err?.data?.error?.message || 'The archive could not be validated.');
    }
  };

  const handleExecute = async () => {
    if (!selectedFile) return;
    setError(null);
    try {
      const job = await executeImport.mutateAsync({
        universeId,
        data: { file: selectedFile },
        params: { conflict_policy: conflictPolicy, dry_run: false },
      });
      setLastJob(job);
      await queryClient.invalidateQueries();
      await refetchJobs();
    } catch (err: any) {
      setError(err?.data?.error?.message || 'The import could not be applied.');
    }
  };

  return (
    <div className="space-y-6">
      <div className="border border-[#d9d1c2] bg-[#faf7ef] p-6">
        <div className="flex items-center gap-2">
          <Download size={18} className="text-[#294238]" />
          <h3 className="font-serif text-lg font-semibold text-[#253a32]">Export Universe</h3>
        </div>
        <p className="mt-1 text-xs text-[#48574d]">
          Download a portable WORLDWEAVE bundle (manifest, JSON records, Markdown with YAML
          frontmatter, referenced assets, and SHA-256 checksums) that opens as an Obsidian vault.
        </p>
        {canExport ? (
          <button
            type="button"
            onClick={handleExport}
            disabled={exportUniverse.isPending}
            className="ww-button mt-4 inline-flex items-center gap-2 border border-[#294238] px-4 py-2 text-xs font-semibold text-[#294238] hover:bg-[#294238] hover:text-[#f7f2e7] disabled:opacity-60"
            data-testid="button-export-universe"
          >
            {exportUniverse.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <FileArchive size={14} />
            )}
            Export as bundle
          </button>
        ) : (
          <p className="mt-4 text-xs italic text-[#899087]">
            Your role does not permit exporting this universe.
          </p>
        )}
      </div>

      {canImport && (
        <div className="border border-[#d9d1c2] bg-[#faf7ef] p-6">
          <div className="flex items-center gap-2">
            <Upload size={18} className="text-[#294238]" />
            <h3 className="font-serif text-lg font-semibold text-[#253a32]">Import Universe</h3>
          </div>
          <p className="mt-1 text-xs text-[#48574d]">
            Upload a bundle to review a dry-run report before applying it. Importing a bundle from
            another universe clones it with fresh IDs; re-importing into the same universe updates
            the existing records.
          </p>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip,application/zip"
              onChange={(e) => {
                const file = e.target.files?.[0] ?? null;
                setSelectedFile(file);
                setValidation(null);
                setLastJob(null);
                setError(null);
              }}
              className="text-xs text-[#253a32] file:mr-3 file:cursor-pointer file:border file:border-[#294238] file:bg-transparent file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-[#294238] hover:file:bg-[#294238] hover:file:text-[#f7f2e7]"
              data-testid="input-import-archive"
            />
            <button
              type="button"
              onClick={() => selectedFile && handleValidate(selectedFile)}
              disabled={!selectedFile || validateImport.isPending}
              className="ww-button inline-flex items-center gap-2 border border-[#294238] px-4 py-2 text-xs font-semibold text-[#294238] hover:bg-[#294238] hover:text-[#f7f2e7] disabled:opacity-50"
              data-testid="button-validate-import"
            >
              {validateImport.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <CheckCircle2 size={14} />
              )}
              Validate archive
            </button>
            {selectedFile && (
              <button
                type="button"
                onClick={resetImport}
                className="text-xs text-[#53655b] underline hover:text-[#9b4a36]"
              >
                Clear
              </button>
            )}
          </div>

          {validation && (
            <div className="mt-5 border border-[#e0d8c8] bg-white p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold text-[#253a32]">
                    Dry-run report
                    {validation.source_universe_name
                      ? ` — from “${validation.source_universe_name}”`
                      : ''}
                  </p>
                  <p className="mt-0.5 text-[11px] text-[#6b6455]">
                    Schema version {validation.schema_version}
                  </p>
                </div>
                <span
                  className={`rounded px-2 py-0.5 text-[11px] font-semibold ${
                    validation.valid
                      ? 'bg-[#e7f1e9] text-[#2f6b45]'
                      : 'bg-[#fbe9e4] text-[#9b4a36]'
                  }`}
                >
                  {validation.valid ? 'Ready to import' : `${validation.report.errors} error(s)`}
                </span>
              </div>

              {validationSummary.length > 0 && (
                <ul className="mt-3 space-y-1 text-[11px] text-[#48574d]">
                  {validationSummary.map((line) => (
                    <li key={line}>• {line}</li>
                  ))}
                </ul>
              )}

              {validation.report.items.length > 0 && (
                <div className="mt-3 max-h-56 overflow-auto border border-[#efe9db]">
                  <table className="w-full text-left text-[11px]">
                    <thead className="bg-[#f5f0e6] text-[#6b6455]">
                      <tr>
                        <th className="px-2 py-1.5 font-semibold">Kind</th>
                        <th className="px-2 py-1.5 font-semibold">Label</th>
                        <th className="px-2 py-1.5 font-semibold">Action</th>
                        <th className="px-2 py-1.5 font-semibold">Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      {validation.report.items.map((item, index) => (
                        <tr key={`${item.kind}-${item.id ?? index}`} className="border-t border-[#efe9db]">
                          <td className="px-2 py-1.5 text-[#48574d]">{item.kind}</td>
                          <td className="px-2 py-1.5 text-[#253a32]">{item.label}</td>
                          <td className="px-2 py-1.5">
                            <span
                              className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${ACTION_STYLES[item.action]}`}
                            >
                              {item.action}
                            </span>
                          </td>
                          <td className="px-2 py-1.5 text-[#6b6455]">{item.message || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {(validation.warnings?.length ?? 0) > 0 && (
                <div className="mt-3 flex gap-2 rounded border border-[#f0e0b8] bg-[#fdf7e8] p-2 text-[11px] text-[#8a6410]">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                  <ul className="space-y-0.5">
                    {validation.warnings?.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="mt-4 flex flex-wrap items-end gap-3 border-t border-[#efe9db] pt-4">
                <div>
                  <label className="block text-[11px] font-semibold text-[#48574d]">
                    Conflict policy
                  </label>
                  <select
                    value={conflictPolicy}
                    onChange={(e) => setConflictPolicy(e.target.value as ConflictPolicy)}
                    className="mt-1 rounded border border-[#d5cebf] bg-white px-2 py-1.5 text-xs text-[#253a32]"
                    data-testid="select-conflict-policy"
                  >
                    <option value="skip">Skip existing records</option>
                    <option value="overwrite">Overwrite existing records</option>
                    <option value="fail">Fail on any conflict</option>
                  </select>
                </div>
                <button
                  type="button"
                  onClick={handleExecute}
                  disabled={!validation.valid || executeImport.isPending}
                  className="ww-button inline-flex items-center gap-2 bg-[#294238] px-4 py-2 text-xs font-semibold text-[#f7f2e7] hover:bg-[#38574a] disabled:opacity-50"
                  data-testid="button-execute-import"
                >
                  {executeImport.isPending ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Upload size={14} />
                  )}
                  Apply import
                </button>
                {!validation.valid && (
                  <p className="text-[11px] text-[#9b4a36]">
                    Resolve the reported errors or choose another archive.
                  </p>
                )}
              </div>
            </div>
          )}

          {lastJob && (
            <div className="mt-4 flex items-start gap-2 rounded border border-[#cfe3d5] bg-[#eef6f0] p-3 text-[11px] text-[#2f6b45]">
              <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
              <div>
                <p className="font-semibold">
                  Import {lastJob.status} with policy “{lastJob.conflict_policy}”.
                </p>
                <p className="mt-0.5 text-[#48574d]">
                  Archive SHA-256 {lastJob.archive_checksum_sha256.slice(0, 12)}…
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded border border-[#e3b7ab] bg-[#fdf2ef] p-3 text-xs text-[#9b4a36]">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <p>{error}</p>
        </div>
      )}

      {canImport && jobs && jobs.total > 0 && (
        <div className="border border-[#d9d1c2] bg-[#faf7ef] p-6">
          <div className="flex items-center gap-2">
            <History size={18} className="text-[#294238]" />
            <h3 className="font-serif text-lg font-semibold text-[#253a32]">Import History</h3>
          </div>
          <ul className="mt-4 space-y-2">
            {jobs.items.map((job) => (
              <li
                key={job.id}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-[#efe9db] pb-2 text-[11px] last:border-0"
              >
                <span className="font-mono text-[#6b6455]">{job.id.slice(0, 8)}…</span>
                <span className="text-[#253a32]">
                  {job.dry_run ? 'dry-run' : job.status} · {job.conflict_policy}
                </span>
                <span className="text-[#899087]">
                  {new Date(job.created_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
