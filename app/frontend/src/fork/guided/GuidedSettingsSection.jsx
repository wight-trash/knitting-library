// Admin settings for guided versions: the on/off switch and the model. Fork-only (FORK.md).
import { useEffect, useState } from 'react';
import { getGuidedSettings, saveGuidedSettings, getGuidedStatus } from '../forkApi';
import { ft } from '../strings';

export default function GuidedSettingsSection() {
  const [settings, setSettings] = useState(null);
  const [configured, setConfigured] = useState(true);
  const [model, setModel] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getGuidedSettings()
      .then((s) => { setSettings(s); setModel(s.model); })
      .catch((e) => setError(e.message));
    getGuidedStatus().then((s) => setConfigured(Boolean(s.configured))).catch(() => {});
  }, []);

  const save = async (values) => {
    setSaving(true); setMessage(''); setError('');
    try {
      const s = await saveGuidedSettings(values);
      setSettings(s); setModel(s.model);
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
            <button
              className={`theme-toggle ${settings.enabled ? 'dark' : ''}`}
              onClick={() => save({ enabled: !settings.enabled })}
              disabled={saving}
              role="switch"
              aria-checked={settings.enabled}
              aria-label={ft('settingsEnable')}
            >
              <span className="theme-toggle-knob" />
            </button>
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
            <button className="btn-primary" onClick={() => save({ model })} disabled={saving || !model.trim() || model === settings.model}>
              {ft('settingsSave')}
            </button>
          </div>
          {message && <p className="settings-row-sub" role="status">{message}</p>}
        </div>
      )}
    </div>
  );
}
