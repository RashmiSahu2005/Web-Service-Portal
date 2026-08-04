import React from 'react';
import { useNavigate } from 'react-router-dom';
import { installApplication } from '../../services/api';

const AppCard = ({ app }) => {
  const navigate = useNavigate();

  const handleInstall = async () => {
    try {
      const response = await installApplication(app.id);
      navigate(`/status/${response.installation_id}`);
    } catch (error) {
      console.error("Installation request failed", error);
    }
  };

  // Determine badge style based on some dummy logic or name
  let badgeText = "STANDARD";
  let badgeClass = "bg-blue-100 text-blue-700";
  if (app.name === "Visual Studio Code" || app.name === "Google Chrome") {
    badgeText = app.name === "Google Chrome" ? "UPDATED" : "APPROVED";
    badgeClass = "bg-green-100 text-green-700";
  } else if (app.name === "Git") {
    badgeText = "CORE";
    badgeClass = "bg-emerald-100 text-emerald-700";
  }

  return (
    <div className="bg-white border border-gray-200 p-6 rounded-xl flex flex-col h-full hover:shadow-lg transition-shadow duration-300 group">
      
      <div className="flex justify-between items-start mb-6">
        <div className="w-12 h-12 rounded-lg bg-gray-50 flex items-center justify-center border border-gray-100 overflow-hidden">
          {/* Simple icon placeholder */}
          <div className="flex space-x-1">
             <div className="w-2 h-2 bg-blue-400 rounded-sm"></div>
             <div className="w-2 h-2 bg-green-400 rounded-sm"></div>
             <div className="w-2 h-2 bg-yellow-400 rounded-sm"></div>
          </div>
        </div>
        <span className={`px-2 py-1 text-[10px] font-bold tracking-wider rounded ${badgeClass}`}>
          {badgeText}
        </span>
      </div>
      
      <div className="flex-1">
        <h3 className="text-xl font-bold text-gray-900 mb-1">{app.name}</h3>
        <p className="text-xs text-gray-500 mb-4">v{app.version} • {app.publisher}</p>
        <p className="text-sm text-gray-600 line-clamp-3 mb-6 leading-relaxed">{app.description}</p>
      </div>
      
      <div className="flex items-center justify-between mt-auto">
        <span className="text-xs font-medium text-gray-500 bg-gray-100 px-3 py-1 rounded">
          {app.category}
        </span>
        <button 
          onClick={handleInstall}
          className="px-6 py-2 bg-[#004aad] hover:bg-[#003882] text-white text-sm font-semibold rounded transition-colors"
        >
          Install
        </button>
      </div>
    </div>
  );
};

export default AppCard;
