const { useState, useEffect } = React;

// Backend URL - use production URL when deployed, localhost for development
const BACKEND_URL = window.location.hostname.includes('run.app') 
    ? 'https://boulder-backend-563085534377.us-central1.run.app'
    : 'http://localhost:8001';

function App() {
    const [query, setQuery] = useState('');
    const [limit, setLimit] = useState(5);
    const [currentJob, setCurrentJob] = useState(null);
    const [jobStatus, setJobStatus] = useState(null);
    const [results, setResults] = useState(null);
    const [error, setError] = useState(null);
    const [pdfs, setPdfs] = useState([]);

    // Convert markdown to sanitized HTML using Marked + DOMPurify
    const markdownToHtml = (text) => {
        if (!text) return '';
        try {
            const html = window.marked.parse(text, { breaks: true });
            return window.DOMPurify.sanitize(html);
        } catch (e) {
            return text;
        }
    };

    const startAnalysis = async () => {
        if (!query.trim()) {
            setError('Please enter a property query');
            return;
        }

        try {
            setError(null);
            setResults(null);
            setJobStatus(null);

            const response = await axios.post(`${BACKEND_URL}/analyze`, {
                query: query,
                limit: limit,
                use_llm: true
            });

            console.log('🚀 Analysis started:', response.data);
            setCurrentJob(response.data.job_id);
            setJobStatus(response.data);
        } catch (err) {
            console.error('❌ Failed to start analysis:', err);
            setError(`Failed to start analysis: ${err.message}`);
        }
    };

    const checkJobStatus = async (jobId) => {
        try {
            const response = await axios.get(`${BACKEND_URL}/job/${jobId}`);
            console.log('📊 Job status response:', response.data);
            setJobStatus(response.data);
            
            if (response.data.status === 'completed') {
                setResults(response.data.results);
                
                // Load PDFs for this job
                try {
                    const pdfsResponse = await axios.get(`${BACKEND_URL}/job/${jobId}/pdfs`);
                    setPdfs(pdfsResponse.data.pdfs);
                } catch (err) {
                    console.log('No PDFs found for this job');
                }
            } else if (response.data.status === 'failed') {
                setError(`Analysis failed: ${response.data.message}`);
            }
        } catch (err) {
            console.error('❌ Failed to check job status:', err);
            setError(`Failed to check job status: ${err.message}`);
        }
    };

    useEffect(() => {
        if (currentJob && jobStatus && jobStatus.status !== 'completed' && jobStatus.status !== 'failed') {
            const interval = setInterval(() => {
                checkJobStatus(currentJob);
            }, 1000);
            return () => clearInterval(interval);
        }
    }, [currentJob, jobStatus]);

    return (
        <div className="min-h-screen bg-gray-100">
            <div className="container mx-auto px-4 py-8">
                <div className="max-w-4xl mx-auto">
                    <h1 className="text-4xl font-bold text-center text-gray-800 mb-8">
                        🏔️ Boulder Property Analyzer
                    </h1>
                    
                    <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Property Query:
                            </label>
                            <input
                                type="text"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Enter property address or subdivision name..."
                                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                        </div>
                        
                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Document Limit:
                            </label>
                            <input
                                type="number"
                                value={limit}
                                onChange={(e) => setLimit(parseInt(e.target.value))}
                                min="1"
                                max="20"
                                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                        </div>
                        
                        <button
                            onClick={startAnalysis}
                            disabled={!query.trim() || (jobStatus && jobStatus.status === 'processing')}
                            className={`w-full py-2 px-4 rounded-md font-medium ${
                                jobStatus && jobStatus.status === 'processing' 
                                    ? 'bg-gray-400 cursor-not-allowed' 
                                    : 'bg-blue-600 hover:bg-blue-700'
                            } text-white`}
                        >
                            {jobStatus && jobStatus.status === 'processing' ? '🔄 Analyzing...' : '🚀 Start Analysis'}
                        </button>
                    </div>

                    {error && (
                        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
                            ❌ {error}
                        </div>
                    )}

                    {jobStatus && jobStatus.status === 'processing' && (
                        <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
                            <h3 className="text-lg font-semibold mb-4">
                                📊 Analysis Progress
                            </h3>
                            <div className="mb-2">
                                <div className="bg-gray-200 rounded-full h-2">
                                    <div 
                                        className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                                        style={{ width: `${jobStatus.progress}%` }}
                                    ></div>
                                </div>
                            </div>
                            <p className="text-sm text-gray-600">
                                {jobStatus.message}
                            </p>
                        </div>
                    )}

                    {results && (
                        <div className="bg-white rounded-lg shadow-lg p-6">
                            <h3 className="text-lg font-semibold mb-4">
                                📖 Analysis Results
                            </h3>
                            <div className="bg-gray-50 p-4 rounded-lg text-sm">
                                {results.results && results.results[0] && results.results[0].llm_analysis && (
                                    <div 
                                        dangerouslySetInnerHTML={{
                                            __html: markdownToHtml(results.results[0].llm_analysis)
                                        }}
                                    />
                                )}
                            </div>
                            
                            {pdfs.length > 0 && (
                                <div className="mt-6">
                                    <h4 className="text-lg font-semibold mb-3">
                                        📄 Downloaded Documents
                                    </h4>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                                        {pdfs.map((pdf, index) => (
                                            <div key={index} className="bg-gray-50 p-3 rounded-lg border">
                                                <div className="flex justify-between items-center">
                                                    <div className="flex-1">
                                                        <p className="font-medium text-sm text-gray-800 truncate">
                                                            {pdf.filename}
                                                        </p>
                                                        <p className="text-xs text-gray-500">
                                                            {(pdf.size / 1024).toFixed(1)} KB
                                                        </p>
                                                    </div>
                                                    <button
                                                        onClick={() => {
                                                            window.open(`${BACKEND_URL}/job/${currentJob}/pdf/${pdf.filename}`, '_blank');
                                                        }}
                                                        className="ml-2 bg-blue-600 text-white px-3 py-1 rounded text-sm hover:bg-blue-700"
                                                    >
                                                        View
                                                    </button>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                            
                            <button
                                onClick={() => {
                                    if (currentJob) {
                                        window.open(`${BACKEND_URL}/job/${currentJob}/report`, '_blank');
                                    }
                                }}
                                className="bg-green-600 text-white py-2 px-4 rounded-md hover:bg-green-700"
                            >
                                📄 Download PDF Report
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

ReactDOM.render(<App />, document.getElementById('root'));
