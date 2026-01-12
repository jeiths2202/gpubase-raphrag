/**
 * Enhance Requests Filter Component
 * Search box, status filter, and refresh button
 */
import React from 'react';
import { Search, RefreshCw } from 'lucide-react';
import { STATUS_OPTIONS } from './utils';

interface EnhanceRequestsFilterProps {
  searchQuery: string;
  statusFilter: string;
  onSearchChange: (query: string) => void;
  onStatusChange: (status: string) => void;
  onRefresh: () => void;
}

export const EnhanceRequestsFilter: React.FC<EnhanceRequestsFilterProps> = ({
  searchQuery,
  statusFilter,
  onSearchChange,
  onStatusChange,
  onRefresh,
}) => {
  return (
    <section className="admin-filters-section">
      <div className="admin-search-box">
        <Search size={18} />
        <input
          type="text"
          placeholder="Search requests..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </div>
      <select
        value={statusFilter}
        onChange={(e) => onStatusChange(e.target.value)}
        className="admin-filter-select"
      >
        {STATUS_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <button className="admin-refresh-btn" onClick={onRefresh}>
        <RefreshCw size={16} />
        Refresh
      </button>
    </section>
  );
};
