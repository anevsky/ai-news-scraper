const scrapeForm = document.getElementById('scrapeForm');
if (scrapeForm) {
    scrapeForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const btn = document.getElementById('scrapeBtn');
        const urlInput = document.getElementById('urlInput');
        const url = urlInput.value;
        const formData = new FormData();
        formData.append('url', url);

        btn.disabled = true;
        btn.innerHTML = '<span class="loading loading-spinner loading-sm"></span> Scraping...';

        // Clear input immediately so user can enter next URL
        urlInput.value = '';

    try {
        const scrapeResponse = await fetch('/scrape', {
            method: 'POST',
            body: formData
        });

        const scrapeData = await scrapeResponse.json();

        if (!scrapeResponse.ok) {
            showToast(`Error: ${scrapeData.detail}`, 'error');
            return;
        }

        // Check if article was a duplicate
        if (scrapeData.status === 'duplicate') {
            showToast('This article has already been scraped', 'warning');
            await refreshArticleHistory();
            return;
        }

        showToast('Article scraped successfully!', 'success');
        await refreshArticleHistory();

    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Scrape';
    }
    });
}

// Semantic search form handler
const searchForm = document.getElementById('searchForm');
if (searchForm) {
    searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const searchInput = document.getElementById('searchInput');
        const searchBtn = document.getElementById('searchBtn');
        const query = searchInput.value.trim();

        if (!query) {
            showToast('Please enter a search query', 'warning');
            return;
        }

        // Show loading state
        if (searchBtn) {
            searchBtn.disabled = true;
            searchBtn.innerHTML = '<span class="loading loading-spinner loading-sm"></span> Searching...';
        }

        // Redirect to search results page
        window.location.href = `/search?query=${encodeURIComponent(query)}`;
    });
}


// Handle analyze and remove buttons in history list
document.addEventListener('click', async (e) => {
    // Find the closest button element (handles clicks on SVG children)
    const analyzeBtn = e.target.closest('.analyze-btn');
    const removeBtn = e.target.closest('.remove-btn');

    if (analyzeBtn) {
        const articleId = parseInt(analyzeBtn.getAttribute('data-article-id'));
        await analyzeArticle(articleId, analyzeBtn);
    } else if (removeBtn) {
        const articleId = parseInt(removeBtn.getAttribute('data-article-id'));
        const articleTitle = removeBtn.getAttribute('data-article-title');
        await deleteArticle(articleId, articleTitle);
    }
});

// Remove All button handler
const removeAllBtn = document.getElementById('removeAllBtn');
if (removeAllBtn) {
    removeAllBtn.addEventListener('click', async () => {
        if (!confirm('Are you sure you want to delete ALL articles? This cannot be undone.')) {
            return;
        }

        const btn = document.getElementById('removeAllBtn');
        btn.disabled = true;
        btn.textContent = 'Deleting...';

        try {
            const response = await fetch('/api/articles', {
                method: 'DELETE'
            });

            const data = await response.json();

            if (response.ok) {
                showToast('All articles deleted successfully', 'success');
                await refreshArticleHistory();
            } else {
                showToast(`Error: ${data.detail}`, 'error');
            }
        } catch (error) {
            showToast(`Error: ${error.message}`, 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = 'Remove All';
        }
    });
}

async function analyzeArticle(articleId, btn) {
    btn.disabled = true;
    const originalHTML = btn.innerHTML;
    btn.innerHTML = '<span class="loading loading-spinner loading-xs"></span> Analyzing...';

    try {
        const response = await fetch(`/analyze/${articleId}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (response.ok) {
            if (data.status === 'already_analyzed') {
                showToast('Article is already analyzed', 'info');
                await refreshArticleHistory();
            } else if (data.status === 'analyzing') {
                showToast('Analysis started! You can continue browsing.', 'success');

                // Add to tracking set immediately
                analyzingArticles.add(articleId);
                saveAnalyzingState();
                startPolling();

                // Refresh the article list to show "Analyzing..." badge
                await refreshArticleHistory();
                return; // Don't re-enable button - it's been replaced by refresh
            }
        } else {
            showToast(`Error: ${data.detail}`, 'error');
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
}

// Track articles being analyzed
// Load from localStorage on page load to persist across refreshes
const storedAnalyzing = localStorage.getItem('analyzingArticles');
const analyzingArticles = new Set(storedAnalyzing ? JSON.parse(storedAnalyzing) : []);
let pollingInterval = null;

// Save analyzingArticles to localStorage whenever it changes
function saveAnalyzingState() {
    localStorage.setItem('analyzingArticles', JSON.stringify([...analyzingArticles]));
}

// Global polling function that checks ALL analyzing articles
async function pollAnalyzingArticles() {
    if (analyzingArticles.size === 0) {
        // No articles analyzing, stop polling
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
        return;
    }

    // Refresh article list to show updated statuses
    await refreshArticleHistory();

    // Check which articles have completed
    const completedArticles = [];
    for (const articleId of analyzingArticles) {
        try {
            const response = await fetch(`/api/article/${articleId}`);
            const data = await response.json();

            if (data.article && data.article.has_analysis) {
                completedArticles.push(articleId);
            }
        } catch (error) {
            console.error(`Error checking article ${articleId}:`, error);
            completedArticles.push(articleId); // Remove from tracking on error
        }
    }

    // Remove completed articles from tracking
    completedArticles.forEach(id => analyzingArticles.delete(id));
    saveAnalyzingState();

    // Show notification if any completed
    if (completedArticles.length > 0) {
        const plural = completedArticles.length > 1 ? 's' : '';
        showToast(`${completedArticles.length} article${plural} analyzed!`, 'success');
    }
}

// Start polling when first article begins analyzing
function startPolling() {
    if (!pollingInterval && analyzingArticles.size > 0) {
        // Poll every 5 seconds
        pollingInterval = setInterval(pollAnalyzingArticles, 5000);
    }
}

async function deleteArticle(articleId, articleTitle) {
    if (!confirm(`Delete article "${articleTitle}"?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/article/${articleId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Article deleted successfully', 'success');
            await refreshArticleHistory();
        } else {
            showToast(`Error: ${data.detail}`, 'error');
        }
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

async function refreshArticleHistory() {
    try {
        const response = await fetch('/api/articles');
        const data = await response.json();

        const historyDiv = document.getElementById('articleHistory');

        if (data.articles.length === 0) {
            historyDiv.innerHTML = '<p class="text-gray-500">No articles scraped yet. Start by entering a URL above.</p>';
            return;
        }

        historyDiv.innerHTML = data.articles.map(article => `
            <div class="card bg-base-200 hover:bg-base-300 transition-colors">
                <div class="card-body p-4">
                    <div class="flex justify-between items-start gap-4">
                        <div class="flex-1">
                            <div class="mb-2">
                                ${
                                    article.has_analysis
                                        ? '<span class="badge badge-success badge-sm">Analyzed</span>'
                                        : analyzingArticles.has(article.id)
                                            ? '<span class="badge badge-info badge-sm"><span class="loading loading-spinner loading-xs mr-1"></span>Analyzing...</span>'
                                            : '<span class="badge badge-warning badge-sm">Scraped</span>'
                                }
                            </div>
                            <h3 class="card-title text-lg mb-2">
                                <a href="/article/${article.id}" class="link link-hover">${article.title || 'Untitled Article'}</a>
                            </h3>
                            ${article.source_domain ? `<div class="text-xs text-gray-500 mb-2"><svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3 inline mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 919-9" /></svg>${article.source_domain}</div>` : ''}
                            ${article.url ? `<p class="text-xs text-gray-500 break-all mb-2"><a href="${article.url}" target="_blank" class="link link-hover">${article.url}</a></p>` : ''}
                            ${article.author ? `<p class="text-sm text-gray-600 mb-2">By ${article.author}</p>` : ''}
                            <div class="text-xs text-gray-500 mb-2 flex gap-3">
                                ${article.scraped_date ? `<span>📥 Scraped: ${article.scraped_date.substring(0, 10)}</span>` : ''}
                                ${article.analyzed_date ? `<span>🤖 Analyzed: ${article.analyzed_date.substring(0, 10)}</span>` : ''}
                            </div>
                            ${article.summary ? `<p class="text-sm mt-2">${article.summary}</p>` : ''}
                            ${article.topics && article.topics.length > 0 ? `<div class="flex gap-2 mt-3 flex-wrap items-center">${article.topics.map(topic => `<a href="/search?query=${encodeURIComponent(topic)}" class="badge badge-primary badge-sm hover:badge-primary-focus cursor-pointer whitespace-nowrap">${topic}</a>`).join('')}</div>` : ''}
                            ${article.has_analysis && (article.analysis_duration_ms || article.analysis_tokens) ? `<div class="flex gap-2 mt-2 flex-wrap items-center">${article.analysis_duration_ms ? `<span class="badge badge-ghost badge-sm">⚡ ${article.analysis_duration_ms}ms</span>` : ''}${article.analysis_tokens ? `<span class="badge badge-ghost badge-sm">🎯 ${article.analysis_tokens} tokens</span>` : ''}</div>` : ''}
                        </div>
                        <div class="flex-shrink-0 flex gap-2">
                            ${!article.has_analysis && !analyzingArticles.has(article.id) ? `<button class="btn btn-sm btn-secondary analyze-btn" data-article-id="${article.id}"><svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>Analyze</button>` : ''}
                            <button class="btn btn-sm btn-ghost btn-square remove-btn" data-article-id="${article.id}" data-article-title="${article.title}" title="Remove article"><svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg></button>
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Failed to refresh article history:', error);
    }
}

function showToast(message, type) {
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toast-message');
    const alert = document.getElementById('toast-alert');

    alert.className = `alert alert-${type}`;
    toastMessage.textContent = message;
    toast.classList.remove('hidden');

    setTimeout(() => {
        toast.classList.add('hidden');
    }, 5000);
}

// Initialize: Start polling if there are analyzing articles from previous session
if (analyzingArticles.size > 0) {
    console.log('Resuming polling for', analyzingArticles.size, 'analyzing articles');
    startPolling();
}
