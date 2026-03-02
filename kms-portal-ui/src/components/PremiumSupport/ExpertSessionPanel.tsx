/**
 * Expert Session Panel
 *
 * Expert-side LiveKit panel for viewing user's shared screen.
 * View-only: no screen share or mic controls for the expert.
 */

import React, { useEffect, useRef, useState } from 'react';
import { X, Monitor, PhoneOff, User } from 'lucide-react';
import { useTranslation } from '../../hooks/useTranslation';

interface ExpertSessionPanelProps {
  token: string;
  serverUrl: string;
  roomName: string;
  userName: string;
  chatContext?: string;
  onEndSession: () => void;
}

export const ExpertSessionPanel: React.FC<ExpertSessionPanelProps> = ({
  token,
  serverUrl,
  roomName: _roomName,
  userName,
  chatContext,
  onEndSession,
}) => {
  const { t } = useTranslation();
  const roomRef = useRef<any>(null);
  const remoteVideoRef = useRef<HTMLVideoElement>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const connectRoom = async () => {
      try {
        const livekitModule = 'livekit-client';
        const { Room, RoomEvent, Track } = await import(/* @vite-ignore */ livekitModule);

        if (cancelled) return;

        const room = new Room();
        roomRef.current = room;

        // Subscribe to remote screen share tracks
        room.on(RoomEvent.TrackSubscribed, (track: any, _pub: any, _participant: any) => {
          if (track.kind === Track.Kind.Video && remoteVideoRef.current) {
            track.attach(remoteVideoRef.current);
          }
        });

        room.on(RoomEvent.TrackUnsubscribed, (track: any) => {
          track.detach();
        });

        room.on(RoomEvent.Disconnected, () => {
          setConnected(false);
        });

        await room.connect(serverUrl, token);
        if (!cancelled) setConnected(true);
      } catch (err) {
        console.error('Expert LiveKit connection failed:', err);
      }
    };

    connectRoom();

    return () => {
      cancelled = true;
      if (roomRef.current) {
        roomRef.current.disconnect();
        roomRef.current = null;
      }
    };
  }, [serverUrl, token]);

  const handleEnd = () => {
    if (roomRef.current) {
      roomRef.current.disconnect();
      roomRef.current = null;
    }
    onEndSession();
  };

  return (
    <div className="expert-session-overlay">
      <div className="expert-session-panel">
        {/* Header */}
        <div className="expert-session-header">
          <div className="expert-session-header-left">
            <Monitor size={20} />
            <h3>{t('common.supportDashboard.expertView')}</h3>
            <span className="expert-session-user-badge">
              <User size={14} />
              {userName}
            </span>
          </div>
          <button className="expert-session-close" onClick={handleEnd}>
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="expert-session-body">
          {chatContext && (
            <div className="expert-session-context">
              <div className="expert-session-context-label">
                {t('common.supportDashboard.chatContext')}
              </div>
              <div className="expert-session-context-text">{chatContext}</div>
            </div>
          )}

          <div className="expert-session-video-area">
            <video
              ref={remoteVideoRef}
              autoPlay
              playsInline
              style={{ width: '100%', height: '100%' }}
            />
            {!connected && (
              <div className="expert-session-video-placeholder">
                <Monitor size={48} />
                <span>{t('common.supportDashboard.waitingForScreen')}</span>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="expert-session-footer">
          <button className="expert-end-session-btn" onClick={handleEnd}>
            <PhoneOff size={16} />
            {t('common.supportDashboard.endSession')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ExpertSessionPanel;
