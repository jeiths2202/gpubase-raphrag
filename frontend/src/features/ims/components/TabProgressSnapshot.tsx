import React from 'react';
import type { ProgressSnapshot } from '../types/progress';

interface TabProgressSnapshotProps {
    progressSnapshot: ProgressSnapshot;
}

export const TabProgressSnapshot: React.FC<TabProgressSnapshotProps> = ({ progressSnapshot }) => {
    return (
        <div style={{
            padding: '12px 16px',
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            fontSize: '13px',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px'
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Final Execution Snapshot</span>
                <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                    {new Date(progressSnapshot.timestamp).toLocaleTimeString()}
                </span>
            </div>

            <div style={{ display: 'flex', gap: '20px' }}>
                <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    <span style={{ color: 'var(--accent)' }}>●</span>
                    <span style={{ color: 'var(--text-secondary)' }}>Issues Found:</span>
                    <span style={{ fontWeight: 600 }}>{progressSnapshot.issuesFound}</span>
                </div>
                <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    <span style={{ color: '#10b981' }}>●</span>
                    <span style={{ color: 'var(--text-secondary)' }}>Issues Crawled:</span>
                    <span style={{ fontWeight: 600 }}>{progressSnapshot.issuesCrawled}</span>
                </div>
                {progressSnapshot.relatedCount !== undefined && (
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                        <span style={{ color: '#f59e0b' }}>●</span>
                        <span style={{ color: 'var(--text-secondary)' }}>Related:</span>
                        <span style={{ fontWeight: 600 }}>{progressSnapshot.relatedCount}</span>
                    </div>
                )}
            </div>
        </div>
    );
};

export default TabProgressSnapshot;
