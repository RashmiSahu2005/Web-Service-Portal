import React, { useState, useEffect } from 'react';
import AppCard from '../../components/AppCard/AppCard.jsx';
import { getApplications } from '../../services/api';
import { Grid, List } from 'lucide-react';

const ApplicationCatalog = () => {
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchApps = async () => {
      try {
        const data = await getApplications();
        setApplications(data);
      } catch (error) {
        console.error("Error fetching applications:", error);
      } finally {
        setLoading(false);
      }
    };
    fetchApps();
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Available Applications</h1>
      </div>

      <div className="flex justify-between items-center">
        {/* Category Filters Simulation */}
        <div className="flex space-x-3 overflow-x-auto pb-2">
          {['All Apps', 'Development', 'Browsers', 'Utilities', 'Productivity'].map(cat => (
            <button 
              key={cat}
              className={`px-5 py-2 rounded-full text-sm font-medium whitespace-nowrap border transition-colors ${
                cat === 'All Apps' 
                  ? 'bg-[#004aad] text-white border-[#004aad]' 
                  : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
        
        <div className="hidden md:flex bg-white border border-gray-200 rounded-lg p-1 space-x-1">
           <button className="p-2 bg-blue-50 text-[#004aad] rounded shadow-sm"><Grid className="w-5 h-5" /></button>
           <button className="p-2 text-gray-400 hover:text-gray-600 rounded"><List className="w-5 h-5" /></button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="w-10 h-10 border-4 border-gray-200 border-t-[#004aad] rounded-full animate-spin"></div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 pb-10">
          {applications.map(app => (
            <AppCard key={app.id} app={app} />
          ))}
        </div>
      )}
    </div>
  );
};

export default ApplicationCatalog;

