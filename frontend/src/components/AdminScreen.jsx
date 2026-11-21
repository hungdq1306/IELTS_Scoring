import {useEffect, useRef, useState} from 'react';
import {api} from '../api';
import {useAuth} from '../auth-context';
import {Notice, Spinner} from '../shared';

const PAGE_SIZE = 25;
const roles = ['student', 'ta', 'teacher', 'admin'];
const auditActions = [
  'admin_user_updated',
  'system_settings_updated',
  'job_retried',
  'profiles_sync_requested',
  'class_created',
  'class_updated',
  'invite_rotated',
  'membership_updated',
  'score_override',
  'profile_updated',
  'anchor_added',
  'anchor_disabled',
  'template_added',
  'template_disabled',
  'prompt_added',
];
const limits = {
  enrolled_student_daily_limit: ['Student daily credits', 100],
  ta_daily_limit: ['TA daily credits', 100],
  teacher_daily_limit: ['Teacher daily credits', 200],
  admin_daily_limit: ['Admin daily credits', 500],
  global_daily_submission_cap: ['System daily submissions', 10000],
};
const date = value => value ? new Date(value * 1000).toLocaleString() : '—';
const fmtSec = value => value == null ? '—' : `${value}s`;

function Pager({offset, total, busy, change}) {
  return <div className="actions admin-pager"><span>{total ? `Showing ${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} of ${total}` : 'No results'}</span><button className="secondary" disabled={busy || !offset} onClick={() => change(offset - PAGE_SIZE)}>Previous page</button><button className="secondary" disabled={busy || offset + PAGE_SIZE >= total} onClick={() => change(offset + PAGE_SIZE)}>Next page</button></div>;
}

function AdminConfirmDialog({title, subject, lines, reason, setReason, showReason = true, confirmLabel = 'Confirm changes', busy = false, onCancel, onConfirm}) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current && !ref.current.open) ref.current.showModal();
    return () => { if (ref.current?.open) ref.current.close(); };
  }, []);
  return <dialog className="submit-dialog" ref={ref} onCancel={onCancel}>
    <h2>{title}</h2>
    {subject && <p><strong>{subject}</strong></p>}
    {!!lines?.length && <ul className="confirm-diff-list">{lines.map((line, i) => <li key={i}>{line}</li>)}</ul>}
    {showReason && <label htmlFor="admin-confirm-reason">Reason note (optional)<input id="admin-confirm-reason" name="confirmReason" value={reason} onChange={e => setReason(e.target.value)} maxLength={1500} placeholder="Recorded in the audit log"/></label>}
    <div className="actions">
      <button type="button" className="secondary" disabled={busy} onClick={onCancel}>Cancel</button>
      <button type="button" className="primary" autoFocus disabled={busy} onClick={onConfirm}>{confirmLabel}</button>
    </div>
  </dialog>;
}

export function AdminScreen({go}) {
  const auth = useAuth();
  const [tab, setTab] = useState('users');
  const [data, setData] = useState(null);
  const [settings, setSettings] = useState(null);
  const [prices, setPrices] = useState([]);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [classFilter, setClassFilter] = useState('');
  const [targetFilter, setTargetFilter] = useState('');
  const [actionFilter, setActionFilter] = useState('');
  const [classOptions, setClassOptions] = useState([]);
  const [activeClassCount, setActiveClassCount] = useState(0);
  const [pendingAction, setPendingAction] = useState(null);
  const [confirmReason, setConfirmReason] = useState('');
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const guard = useRef(false), generation = useRef(0);
  const allowed = auth.account?.role === 'admin';

  async function load(page = offset) {
    const run = ++generation.current;
    setBusy(true); setError('');
    try {
      const query = new URLSearchParams({limit: PAGE_SIZE, offset: page});
      if (search) query.set(tab === 'audit-logs' ? 'actor' : 'search', search);
      if (filter && tab === 'users') query.set('role', filter);
      if (statusFilter && tab === 'users') query.set('is_active', statusFilter);
      if (classFilter && tab === 'users') query.set('class_id', classFilter);
      if (filter && tab === 'jobs') query.set('status', filter);
      if (tab === 'audit-logs') {
        if (targetFilter) query.set('target', targetFilter);
        if (actionFilter) query.set('action', actionFilter);
      }
      const [result, extra] = await Promise.all([
        api('/admin/' + tab + (['users', 'jobs', 'audit-logs'].includes(tab) ? '?' + query : '')),
        tab === 'users' ? api('/teacher/classes').catch(() => null) : tab === 'settings' ? api('/admin/overview').catch(() => null) : Promise.resolve(null),
      ]);
      if (run !== generation.current) return;
      setData(result); setOffset(page);
      if (tab === 'users' && extra?.items) setClassOptions(extra.items);
      if (tab === 'settings') {
        setSettings(result);
        setPrices(Object.entries(result.model_prices_usd_per_million || {}).map(([model, price]) => ({model, ...price})));
        if (extra && typeof extra.active_classes === 'number') setActiveClassCount(extra.active_classes);
      }
    } catch (e) { if (run === generation.current) setError(e.message); }
    finally { if (run === generation.current) setBusy(false); }
  }
  useEffect(() => {
    setData(null); setSettings(null); setMessage('');
    if (allowed) load(0);
    return () => { generation.current++; };
  }, [tab, allowed]);

  async function mutate(fn, success) {
    if (guard.current) return;
    guard.current = true; setBusy(true); setError(''); setMessage('');
    try { const res = await fn(); await load(); setMessage(typeof success === 'function' ? success(res) : success); await auth.refresh(); }
    catch (e) { setError(e.message); }
    finally { guard.current = false; setBusy(false); }
  }
  function switchTab(next) {
    if (next === tab) return;
    generation.current++;
    setData(null); setSettings(null); setSearch(''); setFilter(''); setStatusFilter(''); setClassFilter(''); setTargetFilter(''); setActionFilter(''); setPendingAction(null); setOffset(0); setTab(next);
  }
  if (!allowed) return <section className="surface account-page"><Notice error>Administrator permissions are required.</Notice><div className="actions"><button type="button" className="primary" onClick={() => go?.('overview')}>Back to Studio</button><button type="button" className="secondary" onClick={() => go?.('classes')}>My Classes</button></div></section>;
  return <section className="surface account-page admin-page">
    <h1>Administration</h1><p>Manage accounts, classroom credits and assessment operations.</p>
    <nav className="admin-tabs" aria-label="Administration sections">{Object.entries({users:'Accounts', overview:'Usage overview', jobs:'Grading jobs', 'audit-logs':'Audit logs', settings:'System settings'}).map(([key, label]) => <button key={key} className="secondary" aria-pressed={tab === key} disabled={busy} onClick={() => switchTab(key)}>{label}</button>)}</nav>
    {error && <Notice error>{error}</Notice>}{message && <Notice>{message}</Notice>}
    {['users', 'jobs', 'audit-logs'].includes(tab) && <form onSubmit={e => {e.preventDefault(); load(0);}}>
      <label htmlFor="admin-search">{tab === 'audit-logs' ? 'Search actor name or email' : 'Search name, email or reference'}<input id="admin-search" name="search" value={search} onChange={e => setSearch(e.target.value)} maxLength={200}/></label>
      {tab !== 'audit-logs' && <label htmlFor="admin-filter">{tab === 'users' ? 'Account role' : 'Job status'}<select id="admin-filter" name="filter" value={filter} onChange={e => setFilter(e.target.value)}><option value="">All</option>{(tab === 'users' ? roles : ['QUEUED','SCORING','GENERATING_PRACTICE','FAILED','DONE']).map(value => <option key={value}>{value}</option>)}</select></label>}
      {tab === 'users' && <>
        <label htmlFor="admin-status-filter">Account status<select id="admin-status-filter" name="is_active" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}><option value="">All</option><option value="true">Active</option><option value="false">Suspended</option></select></label>
        <label htmlFor="admin-class-filter">Class<select id="admin-class-filter" name="class_id" value={classFilter} onChange={e => setClassFilter(e.target.value)}><option value="">All classes</option>{classOptions.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      </>}
      {tab === 'audit-logs' && <>
        <label htmlFor="admin-audit-target">Target (name, email or ID)<input id="admin-audit-target" name="target" value={targetFilter} onChange={e => setTargetFilter(e.target.value)} maxLength={200}/></label>
        <label htmlFor="admin-audit-action">Action<select id="admin-audit-action" name="action" value={actionFilter} onChange={e => setActionFilter(e.target.value)}><option value="">All actions</option>{auditActions.map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select></label>
      </>}
      <button className="primary" disabled={busy}>Search</button>
    </form>}
    {busy && !data && <Spinner>Loading administration.</Spinner>}
    {tab === 'users' && data && <>
      {!data.items.length && <p>No matching accounts.</p>}
      {data.items.map(user => {
        const isSelf = user.id === auth.account.id;
        const label = user.display_label || user.full_name || user.email || 'User #' + user.id.slice(0,8);
        return <form key={user.id + ':' + user.role + ':' + user.is_active + ':' + user.bonus_daily_credits} className="admin-user" onSubmit={e => {
          e.preventDefault(); const fields = new FormData(e.currentTarget);
          const nextRole = isSelf ? user.role : fields.get('role');
          const nextBonus = Number(fields.get('bonus'));
          const nextActive = isSelf ? user.is_active : fields.get('active') === 'on';
          const lines = [];
          if (nextRole !== user.role) lines.push(`Role: ${user.role} → ${nextRole}`);
          if (nextBonus !== user.bonus_daily_credits) lines.push(`Bonus daily credits: ${user.bonus_daily_credits} → ${nextBonus}`);
          if (nextActive !== user.is_active) lines.push(`Status: ${user.is_active ? 'Active' : 'Suspended'} → ${nextActive ? 'Active' : 'Suspended'}`);
          if (!lines.length) lines.push(`Bonus daily credits: ${user.bonus_daily_credits} → ${nextBonus}`);
          setConfirmReason(String(fields.get('reason') || ''));
          setPendingAction({
            kind: 'user',
            userId: user.id,
            subject: `${label}${user.email ? ` (${user.email})` : ''}`,
            lines,
            payload: {role: nextRole, bonus_daily_credits: nextBonus, is_active: nextActive},
          });
        }}>
          <div className="admin-record-heading">
            <div className="class-card-header">
              <h2>{label}</h2>
              {isSelf && <span className="topic-badge">Current account (You)</span>}
              <span className={`topic-badge ${user.is_active ? '' : 'amber'}`}>{user.is_active ? 'Active' : 'Suspended'}</span>
            </div>
            {user.email && <p>{user.email}</p>}
            {user.external_auth_id && <p>Clerk ID: <code>{user.external_auth_id}</code></p>}
            <p>{user.remaining_today ?? '—'} / {user.daily_limit ?? '—'} credits remaining today</p>
            <p>{user.classes?.map(c => c.name).join(', ') || 'No active classes'}</p>
          </div>
          <label htmlFor={`user-role-${user.id}`}>Role<select id={`user-role-${user.id}`} name="role" defaultValue={user.role} disabled={busy || isSelf}>{roles.map(role => <option key={role}>{role}</option>)}</select></label>
          <label htmlFor={`user-bonus-${user.id}`}>Bonus daily credits<input id={`user-bonus-${user.id}`} name="bonus" type="number" min="0" max="100" defaultValue={user.bonus_daily_credits} required/></label>
          <label className="consent-choice" htmlFor={`user-active-${user.id}`}><input id={`user-active-${user.id}`} name="active" type="checkbox" defaultChecked={user.is_active} disabled={busy || isSelf}/>Active</label>
          <label htmlFor={`user-reason-${user.id}`}>Reason for change<input id={`user-reason-${user.id}`} name="reason" maxLength={1500}/></label>
          <button className="secondary" disabled={busy}>Save account</button>
        </form>;
      })}
    </>}
    {tab === 'overview' && data && (() => {
      const l24 = data.grading_latency?.['24h'], l7 = data.grading_latency?.['7d'];
      const latencyText = `24h: ${fmtSec(l24?.median_sec)} / ${fmtSec(l24?.p95_sec)} · 7d: ${fmtSec(l7?.median_sec)} / ${fmtSec(l7?.p95_sec)}`;
      const costText = data.estimated_gemini_cost != null && data.pricing_configured !== false ? `$${Number(data.estimated_gemini_cost).toFixed(2)}` : 'Pricing unconfigured';
      return <>
        <div className="admin-metrics">
          <div><span>Submissions today</span><strong>{data.today_submissions ?? 0}</strong><small>{data.completed_today ?? 0} completed · {data.active_classes ?? 0} active classes</small></div>
          <div className={(data.failed_jobs_today || 0) > 0 ? 'kpi-alert' : ''}><span>Failed jobs today</span><strong>{data.failed_jobs_today ?? 0}</strong><small>{(data.failed_jobs_today || 0) > 0 ? 'Requires operator attention' : 'All jobs healthy'}</small></div>
          <div><span>Longest active queue wait</span><strong>{data.longest_active_wait_sec ?? 0}s</strong><small>{data.queue_depth ?? 0} jobs waiting or running</small></div>
          <div><span>Grading latency (Median / P95)</span><strong>{fmtSec(l24?.median_sec)} / {fmtSec(l24?.p95_sec)}</strong><small>{latencyText}</small></div>
          <div><span>AI tokens &amp; cost (7d)</span><strong>{costText}</strong><small>{data.total_tokens_used ?? 0} tokens</small></div>
        </div>
        <p>{data.usage_scope || 'Cost shows Pricing unconfigured when model unit prices or provider usage are unset.'}</p>
        <div className="account-table"><table><caption>Provider usage in the last seven days</caption><thead><tr><th>Day</th><th>Model</th><th>Calls</th><th>Tokens</th><th>Cost (USD)</th></tr></thead><tbody>{(data.usage_by_day_model || []).map(row => <tr key={row.day + row.model}><td>{row.day}</td><td>{row.model}</td><td>{row.calls}</td><td>{row.tokens}</td><td>{row.cost_usd != null ? `$${Number(row.cost_usd).toFixed(4)}` : (row.pricing_status || 'Pricing unconfigured')}</td></tr>)}</tbody></table></div>
      </>;
    })()}
    {tab === 'jobs' && data && <>
      {!data.items.length && <p>No matching jobs.</p>}
      {data.items.map(job => <article className="admin-record" key={job.job_id}><h2>{job.student_name} · {job.submission_code}</h2><p>{job.student_email ? `${job.student_email} · ` : ''}{job.class_name} · {job.kind} · {job.status}</p><p>Submitted {date(job.created_at)} · {job.attempt_count} attempts · {job.wait_duration_sec}s elapsed</p>{job.error_code && <Notice error>{job.error_code}: {job.error_message}</Notice>}{job.credit_refunded && <span className="topic-badge">Credit refunded</span>}{job.status === 'FAILED' && job.kind === 'score' && <form onSubmit={e => {
        e.preventDefault(); const fields = new FormData(e.currentTarget);
        mutate(() => api('/admin/jobs/' + job.submission_id + '/retry', {method:'POST', body:JSON.stringify({reason:fields.get('reason')})}), 'Assessment queued again. A daily credit has been reserved.');
      }}><label htmlFor={`retry-reason-${job.job_id}`}>Reason for retry<input id={`retry-reason-${job.job_id}`} name="reason" required maxLength={1500}/></label><button className="secondary" disabled={busy}>Retry failed assessment</button></form>}</article>)}
    </>}
    {tab === 'audit-logs' && data && <>
      {!data.items.length && <p>No matching audit events.</p>}
      {data.items.map(event => <article className="admin-record" key={event.id}><h2>{event.action_type.replaceAll('_',' ')}</h2><p>{event.actor_name}{event.actor_email ? ` (${event.actor_email})` : ''} → {event.target_label}</p><p>{date(event.created_at)}{event.reason ? ' · ' + event.reason : ''}</p><details><summary>Change details</summary><h3>Before</h3><pre>{JSON.stringify(event.before_json,null,2)}</pre><h3>After</h3><pre>{JSON.stringify(event.after_json,null,2)}</pre></details></article>)}
    </>}
    {tab === 'settings' && settings && <form onSubmit={e => {
      e.preventDefault(); const fields = new FormData(e.currentTarget);
      const body = {};
      for (const key of Object.keys(limits)) {
        const nextVal = Number(fields.get(key));
        if (nextVal !== settings[key]) body[key] = nextVal;
      }
      const nextVersion = fields.get('version');
      if (nextVersion !== settings.active_prompt_version) body.active_prompt_version = nextVersion;
      const nextOffsets = Object.fromEntries(['tr','cc','lr','gra'].map(key => [key, Number(fields.get(key))]));
      if (['tr','cc','lr','gra'].some(key => nextOffsets[key] !== Number(settings.calibration_offsets_json?.[key] || 0))) {
        body.calibration_offsets_json = nextOffsets;
      }
      const models = prices.map(row => row.model.trim());
      if (new Set(models).size !== models.length) { setError('Each model can have only one price entry.'); return; }
      const nextPrices = Object.fromEntries(prices.map(row => [row.model.trim(), {input:Number(row.input),output:Number(row.output)}]));
      const prevPrices = settings.model_prices_usd_per_million || {};
      const pricesChanged = Object.keys(nextPrices).length !== Object.keys(prevPrices).length || Object.keys(nextPrices).some(k => !prevPrices[k] || Number(prevPrices[k].input) !== nextPrices[k].input || Number(prevPrices[k].output) !== nextPrices[k].output);
      if (pricesChanged) body.model_prices_usd_per_million = nextPrices;
      const applyToExisting = fields.get('apply') === 'on';
      const reasonText = String(fields.get('reason') || '').trim();
      if (!Object.keys(body).length && !applyToExisting) {
        setError('No setting changes to save.');
        return;
      }
      if (reasonText) body.reason = reasonText;
      body.apply_to_existing_classes = applyToExisting;
      if (applyToExisting) {
        setConfirmReason(reasonText);
        setPendingAction({
          kind: 'settings',
          subject: `Overwrite daily student quota across all ${activeClassCount} active classes`,
          lines: [`This will overwrite custom daily student quotas on ${activeClassCount} active classes.`],
          payload: body,
        });
        return;
      }
      mutate(() => api('/admin/settings', {method:'PATCH', body:JSON.stringify(body)}), res => res?.affected_classes_count > 0 ? `System settings saved (${res.affected_classes_count} active classes updated).` : 'System settings saved.');
    }} key={JSON.stringify(settings)}>
      {Object.entries(limits).map(([key, [label, max]]) => <label key={key} htmlFor={`setting-${key}`}>{label}<input id={`setting-${key}`} name={key} type="number" min="1" max={max} required defaultValue={settings[key]}/></label>)}
      <label htmlFor="setting-version">Assessment prompt<select id="setting-version" name="version" defaultValue={settings.active_prompt_version}><option value="v1">Calibrated v1</option><option value="v2">Evidence-first v2</option></select></label>
      {['tr','cc','lr','gra'].map(key => <label key={key} htmlFor={`setting-offset-${key}`}>{key.toUpperCase()} calibration offset<input id={`setting-offset-${key}`} name={key} type="number" min="-1" max="1" step="0.01" defaultValue={settings.calibration_offsets_json?.[key] || 0} required/></label>)}
      <fieldset className="model-prices"><legend>Verified model pricing (USD per million tokens)</legend><p>Add exact model names and prices verified for your provider account. Leaving this empty keeps cost estimates unavailable.</p>{prices.map((row, index) => <div className="price-row" key={index}>
        <label htmlFor={`price-model-${index}`}>Model name<input id={`price-model-${index}`} name={`priceModel-${index}`} value={row.model} required pattern=".*\S.*" maxLength={120} onChange={e => setPrices(rows => rows.map((item, i) => i === index ? {...item, model:e.target.value} : item))}/></label>
        {['input','output'].map(kind => <label key={kind} htmlFor={`price-${kind}-${index}`}>{kind === 'input' ? 'Input price' : 'Output price'}<input id={`price-${kind}-${index}`} name={`price-${kind}-${index}`} type="number" min="0" step="any" required value={row[kind]} onChange={e => setPrices(rows => rows.map((item, i) => i === index ? {...item, [kind]:e.target.value} : item))}/></label>)}
        <button className="secondary" type="button" disabled={busy} onClick={() => setPrices(rows => rows.filter((_, i) => i !== index))}>Remove model price</button>
      </div>)}<button className="secondary" type="button" disabled={busy} onClick={() => setPrices(rows => [...rows, {model:'',input:'',output:''}])}>Add model price</button></fieldset>
      <label className="consent-choice" htmlFor="setting-apply-existing"><input id="setting-apply-existing" name="apply" type="checkbox"/>Also overwrite quota for all {activeClassCount} active classes</label>
      <label htmlFor="setting-reason">Reason for change<input id="setting-reason" name="reason" maxLength={1500}/></label>
      <p>New assessments use these settings. Queued assessments retain their original configuration. V2 accuracy requires separate evaluation.</p>
      <button className="primary" disabled={busy}>Save settings</button>
    </form>}
    {data && ['users', 'jobs', 'audit-logs'].includes(tab) && <Pager offset={offset} total={data.total || 0} busy={busy} change={load}/>}
    {pendingAction && <AdminConfirmDialog
      title={pendingAction.kind === 'user' ? 'Confirm account update' : 'Confirm class quota overwrite'}
      subject={pendingAction.subject}
      lines={pendingAction.lines}
      reason={confirmReason}
      setReason={setConfirmReason}
      showReason={pendingAction.kind === 'user'}
      confirmLabel={pendingAction.kind === 'user' ? 'Confirm changes' : 'Confirm overwrite'}
      busy={busy}
      onCancel={() => setPendingAction(null)}
      onConfirm={() => {
        const action = pendingAction;
        const reason = confirmReason;
        setPendingAction(null);
        if (action.kind === 'user') {
          mutate(() => api('/admin/users/' + action.userId, {method:'PATCH', body:JSON.stringify({...action.payload, reason})}), 'Account updated.');
        } else {
          mutate(() => api('/admin/settings', {method:'PATCH', body:JSON.stringify(action.payload)}), res => res?.affected_classes_count > 0 ? `System settings saved (${res.affected_classes_count} active classes updated).` : 'System settings saved.');
        }
      }}
    />}
  </section>;
}
