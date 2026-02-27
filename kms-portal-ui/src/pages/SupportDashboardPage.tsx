/**
 * Support Dashboard Page
 *
 * Shows all support sessions for senior+ experts.
 * Waiting sessions can be joined; active sessions can be ended.
 */

import React, { useState, useCallback, useMemo } from 'react';
import {
  Headphones,
  RefreshCw,
  Clock,
  Zap,
  BarChart3,
  User,
  Inbox,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import { useSupportSessions } from '../hooks/useSupportSessions';
import { premiumSupportApi, type JoinSessionResponse } from '../api/premium-support.api';
import { ExpertSessionPanel } from '../components/PremiumSupport/ExpertSessionPanel';
import './SupportDashboardPage.css';

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return '<1m';
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ${mins % 60}m`;
}

export const SupportDashboardPage: React.FC = () => {
  const { t } = useTranslation();
  const { sessions, waitingCount, activeCount, refresh } = useSupportSessions();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [joiningRoom, setJoiningRoom] = useState<string | null>(null);
  const [activeSession, setActiveSession] = useState<JoinSessionResponse | null>(null);

  const waitingSessions = useMemo(
    () => sessions.filter((s) => s.status === 'waiting'),
    [sessions]
  );
  const activeSessions = useMemo(
    () => sessions.filter((s) => s.status === 'active'),
    [sessions]
  );

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await refresh();
    setTimeout(() => setIsRefreshing(false), 600);
  }, [refresh]);

  const handleJoin = useCallback(async (roomName: string) => {
    setJoiningRoom(roomName);
    try {
      // Request notification permission on first join
      if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
      }
      const response = await premiumSupportApi.joinSession(roomName);
      const data = (response as any).data?.data ?? (response as any).data ?? response.data;
      setActiveSession(data);
    } catch (err) {
      console.error('Failed to join session:', err);
    } finally {
      setJoiningRoom(null);
    }
  }, []);

  const handleEndSession = useCallback(async (roomName: string) => {
    try {
      await premiumSupportApi.endSession({ room_name: roomName });
      setActiveSession(null);
      refresh();
    } catch (err) {
      console.error('Failed to end session:', err);
    }
  }, [refresh]);

  const totalToday = sessions.length;

  return (
    <div className="support-dashboard">
      {/* Header */}
      <div className="support-dashboard-header">
        <h1>
          <Headphones size={24} />
          {t('common.supportDashboard.title')}
        </h1>
        <button
          className={`support-dashboard-refresh ${isRefreshing ? 'spinning' : ''}`}
          onClick={handleRefresh}
        >
          <RefreshCw size={16} />
          {t('common.refresh')}
        </button>
      </div>

      {/* Stats Bar */}
      <div className="support-stats-bar">
        <div className="support-stat-card">
          <div className="support-stat-icon waiting">
            <Clock size={22} />
          </div>
          <div className="support-stat-info">
            <span className="support-stat-value">{waitingCount}</span>
            <span className="support-stat-label">{t('common.supportDashboard.waiting')}</span>
          </div>
        </div>
        <div className="support-stat-card">
          <div className="support-stat-icon active">
            <Zap size={22} />
          </div>
          <div className="support-stat-info">
            <span className="support-stat-value">{activeCount}</span>
            <span className="support-stat-label">{t('common.supportDashboard.active')}</span>
          </div>
        </div>
        <div className="support-stat-card">
          <div className="support-stat-icon total">
            <BarChart3 size={22} />
          </div>
          <div className="support-stat-info">
            <span className="support-stat-value">{totalToday}</span>
            <span className="support-stat-label">{t('common.supportDashboard.totalToday')}</span>
          </div>
        </div>
      </div>

      {/* Waiting Sessions */}
      <div className="support-section">
        <div className="support-section-header">
          {t('common.supportDashboard.waitingSessions')}
          <span className="support-section-count waiting">{waitingCount}</span>
        </div>
        {waitingSessions.length === 0 ? (
          <div className="support-empty">
            <Inbox size={40} />
            <p>{t('common.supportDashboard.noSessions')}</p>
          </div>
        ) : (
          <div className="support-session-list">
            {waitingSessions.map((session) => (
              <div key={session.session_id} className="support-session-card waiting">
                <div className="support-session-avatar">
                  <User size={20} />
                </div>
                <div className="support-session-info">
                  <div className="support-session-name">{session.user_name}</div>
                  {session.chat_context && (
                    <div className="support-session-context">
                      {session.chat_context}
                    </div>
                  )}
                </div>
                <div className="support-session-meta">
                  <span className="support-session-time">{timeAgo(session.created_at)}</span>
                </div>
                <div className="support-session-actions">
                  <button
                    className="support-join-btn"
                    onClick={() => handleJoin(session.room_name)}
                    disabled={joiningRoom === session.room_name}
                  >
                    {joiningRoom === session.room_name
                      ? t('common.loading')
                      : t('common.supportDashboard.joinSession')}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Active Sessions */}
      <div className="support-section">
        <div className="support-section-header">
          {t('common.supportDashboard.activeSessions')}
          <span className="support-section-count active">{activeCount}</span>
        </div>
        {activeSessions.length === 0 ? (
          <div className="support-empty">
            <Inbox size={40} />
            <p>{t('common.supportDashboard.noActiveSessions')}</p>
          </div>
        ) : (
          <div className="support-session-list">
            {activeSessions.map((session) => (
              <div key={session.session_id} className="support-session-card active">
                <div className="support-session-avatar">
                  <User size={20} />
                </div>
                <div className="support-session-info">
                  <div className="support-session-name">{session.user_name}</div>
                  {session.chat_context && (
                    <div className="support-session-context">
                      {session.chat_context}
                    </div>
                  )}
                </div>
                <div className="support-session-meta">
                  <span className="support-session-time">{timeAgo(session.created_at)}</span>
                  {session.expert_name && (
                    <span className="support-session-expert">
                      Expert: {session.expert_name}
                    </span>
                  )}
                </div>
                <div className="support-session-actions">
                  <button
                    className="support-end-btn"
                    onClick={() => handleEndSession(session.room_name)}
                  >
                    {t('common.supportDashboard.endSession')}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Expert Session Panel (overlay when joined) */}
      {activeSession && (
        <ExpertSessionPanel
          token={activeSession.token}
          serverUrl={activeSession.server_url}
          roomName={activeSession.room_name}
          userName={activeSession.user_name}
          chatContext={activeSession.chat_context}
          onEndSession={() => handleEndSession(activeSession.room_name)}
        />
      )}
    </div>
  );
};

export default SupportDashboardPage;
