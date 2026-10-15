import React from 'react';
import { ExternalLink, Github } from 'lucide-react';
import { useApp } from '../utils/AppContext';
import { getLanguageLocale } from '../utils/translations';
import './AnnouncementModal.css';
import { releaseText } from '../fork/releases/releaseText'; // fork: no raw HTML in release notes

/**
 * Shows one or more unread GitHub releases to the user.
 * Dismisses all of them when "Got it!" is clicked.
 */
export default function AnnouncementModal({ announcements, onDismiss }) {
  const { t, language } = useApp();
  if (!announcements || announcements.length === 0) return null;

  // Show the most recent announcement (first in the sorted list)
  const latest = announcements[0];
  const remaining = announcements.length - 1;

  const formatDate = (iso) => {
    try {
      return new Date(iso).toLocaleDateString(
        getLanguageLocale(language),
        { year: 'numeric', month: 'short', day: 'numeric' }
      );
    }
    catch { return iso; }
  };

  return (
    <div className="ann-overlay" role="dialog" aria-modal="true" aria-labelledby="ann-title">
      <div className="ann-modal">
        <div className="ann-header">
          <div className="ann-icon">
            <Github size={20} />
          </div>
          <div className="ann-header-text">
            <span className="ann-label">{latest.prerelease ? t('releasePrerelease') : t('githubReleaseNotes')}</span>
            <h2 className="ann-title" id="ann-title">{latest.title || latest.name || latest.tag_name}</h2>
            {latest.tag_name && <span className="ann-tag">{latest.tag_name}</span>}
          </div>
        </div>

        {releaseText(latest.body) && ( // fork
          <div className="ann-body">
            <pre className="ann-body-text">{releaseText(latest.body)}</pre>{/* fork */}
          </div>
        )}

        <div className="ann-footer">
          <div className="ann-meta">
            {formatDate(latest.published_at || latest.created_at)}
            {remaining > 0 && (
              <span className="ann-more"> · {t('releaseMoreUpdates').replace('{COUNT}', remaining)}</span>
            )}
          </div>
          {latest.html_url && (
            <a className="ann-link-btn" href={latest.html_url} target="_blank" rel="noreferrer">
              <ExternalLink size={14} />
              <span>{t('openOnGitHub')}</span>
            </a>
          )}
          <button className="ann-dismiss-btn" onClick={onDismiss} autoFocus>
            {t('gotIt')}
          </button>
        </div>
      </div>
    </div>
  );
}
