import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { KeyRound, Copy, RotateCw, Trash2, Plus } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

interface ApiKeyItem {
  id: number;
  key_prefix: string;
  label: string;
  version_tag: string | null;
  created_at: string;
  last_used_at: string | null;
  revoked: boolean;
}

interface Props {
  fnName: string;
  publicId?: string;
  token: string | null;
}

export default function ApiAccessPanel({ fnName, publicId, token }: Props) {
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [label, setLabel] = useState('');
  const [pinVersion, setPinVersion] = useState('');
  const [newKey, setNewKey] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');

  const headers = { headers: { Authorization: `Bearer ${token}` } };
  const base = `${API_BASE}/functions/${fnName}/keys`;
  // Absolute URL that callers outside the dashboard should use
  const origin = API_BASE.startsWith('http') ? API_BASE : `${window.location.origin}${API_BASE}`;
  const endpoint = `${origin}/f/${publicId ?? '<public_id>'}`;

  const load = useCallback(async () => {
    if (!fnName || !token) return;
    try {
      const resp = await axios.get(base, { headers: { Authorization: `Bearer ${token}` } });
      setKeys(resp.data);
      setError('');
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Could not load API keys');
    }
  }, [fnName, token, base]);

  useEffect(() => {
    setNewKey(null);
    setKeys([]);
    load();
  }, [load]);

  const copy = (text: string, id: string) => {
    navigator.clipboard?.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(''), 1500);
  };

  const create = async () => {
    try {
      const resp = await axios.post(base, {
        label: label.trim() || 'default',
        version_tag: pinVersion.trim() || null,
      }, headers);
      setNewKey(resp.data.api_key);
      setLabel('');
      setPinVersion('');
      load();
    } catch (e: any) {
      const d = e.response?.data?.detail;
      setError(typeof d === 'string' ? d : 'Could not create key (check the version pin format)');
    }
  };

  const rotate = async (id: number) => {
    try {
      const resp = await axios.post(`${base}/${id}/rotate`, {}, headers);
      setNewKey(resp.data.api_key);
      load();
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Could not rotate key');
    }
  };

  const revoke = async (id: number) => {
    if (!window.confirm('Revoke this key? Anything using it will stop working immediately.')) return;
    try {
      await axios.delete(`${base}/${id}`, headers);
      load();
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Could not revoke key');
    }
  };

  const keyText = newKey ?? '<your_api_key>';
  const curl = `curl -X POST ${endpoint} \\\n  -H "X-API-Key: ${keyText}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"name": "World"}'`;
  const python = `import requests\n\nresp = requests.post(\n    "${endpoint}",\n    headers={"X-API-Key": "${keyText}"},\n    json={"name": "World"},\n)\nprint(resp.json()["result"])`;

  if (!fnName) return null;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 mt-6">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2">
        <KeyRound className="w-5 h-5 text-amber-400" /> API Access for <span className="font-mono">{fnName}</span>
      </h2>
      <p className="text-xs text-slate-400">
        Call this function from your own apps with an API key. A key works for this function only, and can optionally be pinned to one version.
      </p>

      <div className="p-3 bg-slate-950/70 border border-slate-800 rounded-lg text-xs font-mono text-slate-300 flex items-center justify-between gap-2">
        <span className="break-all">POST {endpoint}</span>
        <button onClick={() => copy(endpoint, 'endpoint')} className="text-blue-400 hover:text-blue-300 shrink-0" title="Copy endpoint">
          {copied === 'endpoint' ? <span className="text-[10px]">Copied</span> : <Copy className="w-4 h-4" />}
        </button>
      </div>

      {newKey && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/40 rounded-lg space-y-2">
          <div className="text-xs font-semibold text-amber-300">Copy this key now. It will not be shown again.</div>
          <div className="flex items-center gap-2">
            <code className="flex-1 break-all text-xs text-amber-100 bg-slate-950 p-2 rounded">{newKey}</code>
            <button onClick={() => copy(newKey, 'key')} className="px-2.5 py-1.5 text-xs bg-amber-600 hover:bg-amber-500 text-white rounded">
              {copied === 'key' ? 'Copied' : 'Copy'}
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2 items-end">
        <div>
          <label className="block text-[10px] uppercase tracking-wider text-slate-400 mb-1">Label</label>
          <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="mobile app"
            className="px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-blue-500" />
        </div>
        <div>
          <label className="block text-[10px] uppercase tracking-wider text-slate-400 mb-1">Pin to version (optional)</label>
          <input value={pinVersion} onChange={(e) => setPinVersion(e.target.value)} placeholder="v1"
            className="w-32 px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-blue-500" />
        </div>
        <button onClick={create} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg flex items-center gap-1.5">
          <Plus className="w-4 h-4" /> Create API key
        </button>
      </div>

      {error && <div className="text-xs text-red-400">{error}</div>}

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-300">
          <thead className="text-slate-400 uppercase text-[10px] border-b border-slate-800">
            <tr>
              <th className="p-2">Key</th>
              <th className="p-2">Label</th>
              <th className="p-2">Version</th>
              <th className="p-2">Last used</th>
              <th className="p-2">Status</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {keys.length === 0 && (
              <tr><td colSpan={6} className="p-3 text-slate-500">No API keys yet.</td></tr>
            )}
            {keys.map(k => (
              <tr key={k.id} className="border-b border-slate-800/60">
                <td className="p-2 font-mono">{k.key_prefix}…</td>
                <td className="p-2">{k.label}</td>
                <td className="p-2">{k.version_tag || 'latest'}</td>
                <td className="p-2">{k.last_used_at ? new Date(k.last_used_at + 'Z').toLocaleString() : 'never'}</td>
                <td className="p-2">{k.revoked ? <span className="text-red-400">revoked</span> : <span className="text-emerald-400">active</span>}</td>
                <td className="p-2 text-right whitespace-nowrap">
                  {!k.revoked && (
                    <>
                      <button onClick={() => rotate(k.id)} className="text-slate-400 hover:text-blue-400 mr-3" title="Rotate">
                        <RotateCw className="w-4 h-4 inline" />
                      </button>
                      <button onClick={() => revoke(k.id)} className="text-slate-400 hover:text-red-400" title="Revoke">
                        <Trash2 className="w-4 h-4 inline" />
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {[['curl', curl], ['Python', python]].map(([title, code]) => (
          <div key={title} className="relative">
            <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">{title}</div>
            <pre className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-[11px] text-slate-200 overflow-x-auto">{code}</pre>
            <button onClick={() => copy(code, title)} className="absolute top-5 right-2 text-slate-400 hover:text-blue-400" title="Copy">
              {copied === title ? <span className="text-[10px]">Copied</span> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
