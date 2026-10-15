// Admin settings card "Knitting upgrades": the switches for guided versions and the stash in grams, and the AI
// model they use. Fork-only (FORK.md). Mounted by SettingsPage.jsx under the same menu entry as before.
import { useEffect, useState } from 'react';
import { getForkSettings, saveForkSettings, getGuidedStatus } from '../forkApi';
import { forgetGuidedStatus } from './useGuidedStatus';
import { forgetStashStatus } from '../stash/stashStore';
import { ft } from '../strings';
import '../stash/Stash.css';

function Switch({ on, onToggle, disabled, label }) {
  return (
    <button
      type="button"
      className="ku-switch"
      onClick={onToggle}
      disabled={disabled}
      role="switch"
      aria-checked={on}
      aria-label={label}
    >
      <span className={`theme-toggle ${on ? 'dark' : ''}`} aria-hidden="true">
        <span className="theme-toggle-knob" />
      </span>
    </button>
  );
}

export default function GuidedSettingsSection() {
  const [settings, setSettings] = useState(null);
  const [configured, setConfigured] = useState(true);
  const [model, setModel] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getForkSettings()
      .then((s) => { setSettings(s); setModel(s.guide_model); })
      .catch((e) => setError(e.message));
    getGuidedStatus().then((s) => setConfigured(Boolean(s.configured))).catch(() => {});
  }, []);

  const save = async (values) => {
    setSaving(true); setMessage(''); setError('');
    try {
      const s = await saveForkSettings(values);
      setSettings(s); setModel(s.guide_model);
      forgetGuidedStatus();
      forgetStashStatus();
      setMessage(ft('settingsSaved'));
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (!settings && !error) return <div className="settings-section"><p className="loading-text">{ft('loading')}</p></div>;

  return (
    <div className="settings-section">
      <h3 className="section-heading">{ft('settingsTitle')}</h3>
      <p className="settings-row-sub ai-section-intro">{ft('settingsIntro')}</p>
      {error && <p className="settings-row-sub" role="alert">{error}</p>}
      {settings && (
        <div className="form-stack ai-settings-form">
          <div className="ai-settings-card ai-enable-card">
            <div className="settings-row-info">
              <p className="settings-row-label">{ft('settingsEnable')}</p>
              <p className="settings-row-sub">{ft('settingsEnableSub')}</p>
            </div>
            <Switch
              on={settings.guides_enabled}
              onToggle={() => save({ guides_enabled: !settings.guides_enabled })}
              disabled={saving}
              label={ft('settingsEnable')}
            />
          </div>
          <div className="ai-settings-card ai-enable-card">
            <div className="settings-row-info">
              <p className="settings-row-label">{ft('settingsStash')}</p>
              <p className="settings-row-sub">{ft('settingsStashSub')}</p>
            </div>
            <Switch
              on={settings.stash_enabled}
              onToggle={() => save({ stash_enabled: !settings.stash_enabled })}
              disabled={saving}
              label={ft('settingsStash')}
            />
          </div>
          {!configured && <p className="settings-row-sub" role="note">{ft('settingsNeedsAI')}</p>}
          <div className="ai-settings-card">
            <div className="settings-row-info">
              <p className="settings-row-label">{ft('settingsModel')}</p>
              <p className="settings-row-sub">{ft('settingsModelSub')}</p>
            </div>
            <input
              className="form-input"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              aria-label={ft('settingsModel')}
              spellCheck={false}
              autoCapitalize="off"
            />
            <button className="btn-primary" onClick={() => save({ guide_model: model })} disabled={saving || !model.trim() || model === settings.guide_model}>
              {ft('settingsSave')}
            </button>
          </div>
          {message && <p className="settings-row-sub" role="status">{message}</p>}
        </div>
      )}
    </div>
  );
}
