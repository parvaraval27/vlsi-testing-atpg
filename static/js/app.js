        const netlistsContainer = document.getElementById('netlistsContainer');
        const algoBasic = document.getElementById('algoBasic');
        const algoD = document.getElementById('algoD');
        const algoPODEM = document.getElementById('algoPODEM');
        const runBtn = document.getElementById('runBtn');
        const runDseBtn = document.getElementById('runDseBtn');
        const runDsePodemVariantsBtn = document.getElementById('runDsePodemVariantsBtn');
        const runDseDVariantsBtn = document.getElementById('runDseDVariantsBtn');
        const runDseSimKernelsBtn = document.getElementById('runDseSimKernelsBtn');
        const runDseFillVariantsBtn = document.getElementById('runDseFillVariantsBtn');
        const dseIterativeMode = document.getElementById('dseIterativeMode');
        const dseIterationsInput = document.getElementById('dseIterationsInput');
        const metricCoverage = document.getElementById('metricCoverage');
        const metricTime = document.getElementById('metricTime');
        const metricBacktracks = document.getElementById('metricBacktracks');
        const metricMemory = document.getElementById('metricMemory');
        const metricTestVectors = document.getElementById('metricTestVectors');
        const status = document.getElementById('status');
        const results = document.getElementById('results');
        const dseResultsPrimary = document.getElementById('dseResultsPrimary');
        const dseResultsPodemVariants = document.getElementById('dseResultsPodemVariants');
        const dseResultsDVariants = document.getElementById('dseResultsDVariants');
        const dseResultsSimKernels = document.getElementById('dseResultsSimKernels');
        const dseResultsFillVariants = document.getElementById('dseResultsFillVariants');
        const outAtpg = document.getElementById('outAtpg');
        const outDse1 = document.getElementById('outDse1');
        const outDse2 = document.getElementById('outDse2');
        const outDse3 = document.getElementById('outDse3');
        const outDse4 = document.getElementById('outDse4');
        const outDse5 = document.getElementById('outDse5');

        const outputPanels = {
            atpg: outAtpg,
            dse1: outDse1,
            dse2: outDse2,
            dse3: outDse3,
            dse4: outDse4,
            dse5: outDse5,
        };

        function setOutputPanelState(panel, isOpen) {
            if (!panel) return;
            panel.open = isOpen;
            const summary = panel.querySelector('summary');
            if (summary) {
                summary.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            }
        }

        function collapseAllOutputPanels() {
            Object.values(outputPanels).forEach(panel => setOutputPanelState(panel, false));
        }

        function focusOutputPanel(panelKey) {
            collapseAllOutputPanels();
            const panel = outputPanels[panelKey];
            if (!panel) return;
            setOutputPanelState(panel, true);
            panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        function initOutputCollapsibles() {
            document.querySelectorAll('.output-collapse > summary').forEach(summary => {
                const panel = summary.parentElement;
                summary.setAttribute('aria-expanded', panel.open ? 'true' : 'false');

                summary.addEventListener('click', (event) => {
                    event.preventDefault();
                    setOutputPanelState(panel, !panel.open);
                });
            });

            collapseAllOutputPanels();
        }

        function getSelectedNetlists() {
            return Array.from(document.querySelectorAll('.netlist-cb:checked')).map(cb => cb.value);
        }

        function getSelectedMetrics() {
            const selectedMetrics = [];
            if (metricCoverage.checked) selectedMetrics.push('coverage');
            if (metricTime.checked) selectedMetrics.push('time');
            if (metricBacktracks.checked) selectedMetrics.push('backtracks');
            if (metricMemory.checked) selectedMetrics.push('memory');
            if (metricTestVectors.checked) selectedMetrics.push('test_vectors');
            return selectedMetrics;
        }

        function sanitizeIterations(rawValue) {
            const n = Number(rawValue);
            if (!Number.isFinite(n)) return null;
            const rounded = Math.round(n);
            if (rounded < 1 || rounded > 10) return null;
            return rounded;
        }

        function getDseExecutionSettings() {
            const iterative = !!(dseIterativeMode && dseIterativeMode.checked);
            if (!iterative) {
                return { iterative: false, iterations: null };
            }

            let iterations = sanitizeIterations(dseIterationsInput ? dseIterationsInput.value : null);
            if (iterations === null) {
                const promptValue = window.prompt('Enter number of iterations (1-10):', dseIterationsInput ? dseIterationsInput.value || '3' : '3');
                if (promptValue === null) {
                    return null;
                }
                iterations = sanitizeIterations(promptValue);
            }

            if (iterations === null) {
                status.textContent = 'Iterations must be an integer between 1 and 10.';
                status.classList.add('error');
                return null;
            }

            if (dseIterationsInput) {
                dseIterationsInput.value = String(iterations);
            }

            return { iterative: true, iterations };
        }

        function initDseExecutionControls() {
            if (!dseIterativeMode || !dseIterationsInput) return;

            const syncState = () => {
                const enabled = dseIterativeMode.checked;
                dseIterationsInput.disabled = !enabled;
                dseIterationsInput.style.background = enabled ? '#ffffff' : '#f6f7f9';
            };

            dseIterativeMode.addEventListener('change', syncState);
            dseIterationsInput.addEventListener('change', () => {
                const validated = sanitizeIterations(dseIterationsInput.value);
                if (validated === null) {
                    dseIterationsInput.value = '3';
                } else {
                    dseIterationsInput.value = String(validated);
                }
            });

            syncState();
        }

        async function loadNetlists() {
            try {
                const resp = await fetch('/api/netlists');
                const data = await resp.json();
                const netlists = data.netlists || [];

                if (netlists.length === 0) {
                    netlistsContainer.innerHTML = '<p style="margin: 0; color: #999; font-size: 13px;">No netlists found.</p>';
                    return;
                }

                netlistsContainer.innerHTML = netlists.map(nl => `
                    <label style="display: flex; align-items: center; gap: 8px; font-weight: 400; text-transform: none; margin: 0; color: #10243f; cursor: pointer;">
                        <input type="checkbox" class="netlist-cb" value="${nl}" checked />
                        <span style="font-size: 13px;">${nl}</span>
                    </label>
                `).join('');

                status.textContent = `Loaded ${netlists.length} netlists.`;
                status.classList.remove('running', 'error');
            } catch (err) {
                status.textContent = 'Failed to load netlists: ' + err.message;
                status.classList.add('error');
            }
        }

        async function runATPC() {
            const selectedNetlists = getSelectedNetlists();
            const selectedAlgos = [];
            if (algoBasic.checked) selectedAlgos.push('BASIC');
            if (algoD.checked) selectedAlgos.push('D');
            if (algoPODEM.checked) selectedAlgos.push('PODEM');

            if (selectedNetlists.length === 0) {
                status.textContent = 'Please select at least one netlist.';
                status.classList.add('error');
                return;
            }

            if (selectedAlgos.length === 0) {
                status.textContent = 'Please select at least one algorithm.';
                status.classList.add('error');
                return;
            }

            runBtn.disabled = true;
            status.textContent = `Running ${selectedAlgos.join('+')} on ${selectedNetlists.length} netlist(s)...`;
            status.classList.add('running');
            status.classList.remove('error');
            focusOutputPanel('atpg');
            results.innerHTML = '';

            try {
                const resp = await fetch('/api/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ netlists: selectedNetlists, algorithms: selectedAlgos })
                });

                if (!resp.ok) {
                    throw new Error('Server error: ' + resp.status);
                }

                const data = await resp.json();

                if (data.error) {
                    status.textContent = 'Error: ' + data.error;
                    status.classList.add('error');
                    results.innerHTML = '<div class="empty">' + data.error + '</div>';
                    return;
                }

                status.textContent = `Rendered ${(data.results || []).length} result block(s).`;
                status.classList.remove('running', 'error');
                status.classList.add('success');
                renderResults(data.results || []);
            } catch (err) {
                status.textContent = 'Run failed: ' + err.message;
                status.classList.add('error');
                results.innerHTML = '<div class="empty">' + err.message + '</div>';
            } finally {
                runBtn.disabled = false;
            }
        }

        async function runDSE() {
            const selectedNetlists = getSelectedNetlists();
            if (selectedNetlists.length === 0) {
                status.textContent = 'Please select at least one netlist for DSE.';
                status.classList.add('error');
                return;
            }

            const dseMode = getDseExecutionSettings();
            if (!dseMode) return;

            const selectedMetrics = getSelectedMetrics();
            if (selectedMetrics.length === 0) {
                status.textContent = 'Select at least one metric for DSE.';
                status.classList.add('error');
                return;
            }

            runDseBtn.disabled = true;
            status.textContent = dseMode.iterative
                ? `Running DSE #1 (${dseMode.iterations} iterations) on ${selectedNetlists.length} netlist(s)...`
                : `Running DSE #1 on ${selectedNetlists.length} netlist(s)...`;
            status.classList.add('running');
            status.classList.remove('error');
            focusOutputPanel('dse1');
            dseResultsPrimary.innerHTML = '';

            try {
                const endpoint = dseMode.iterative ? '/api/dse-iterative' : '/api/dse';
                const requestBody = {
                    netlists: selectedNetlists,
                    metrics: selectedMetrics,
                    ...(dseMode.iterative ? { iterations: dseMode.iterations } : {}),
                };

                const resp = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });

                if (!resp.ok) {
                    throw new Error('Server error: ' + resp.status);
                }

                const data = await resp.json();
                if (data.error) {
                    status.textContent = 'DSE error: ' + data.error;
                    status.classList.add('error');
                    dseResultsPrimary.innerHTML = '<div class="empty">' + data.error + '</div>';
                    return;
                }

                status.textContent = `DSE #1 complete: ${(data.comparisons || []).length} netlist comparison(s).`;
                status.classList.remove('running', 'error');
                status.classList.add('success');
                renderDseResults(data.comparisons || [], selectedMetrics, dseResultsPrimary, 'DSE #1', 'd_variants', dseMode.iterative);
            } catch (err) {
                status.textContent = 'DSE failed: ' + err.message;
                status.classList.add('error');
                dseResultsPrimary.innerHTML = '<div class="empty">' + err.message + '</div>';
            } finally {
                runDseBtn.disabled = false;
            }
        }

        async function runDsePodemVariants() {
            const selectedNetlists = getSelectedNetlists();
            if (selectedNetlists.length === 0) {
                status.textContent = 'Please select at least one netlist for DSE #2.';
                status.classList.add('error');
                return;
            }

            const dseMode = getDseExecutionSettings();
            if (!dseMode) return;

            const selectedMetrics = getSelectedMetrics();
            if (selectedMetrics.length === 0) {
                status.textContent = 'Select at least one metric for DSE #2.';
                status.classList.add('error');
                return;
            }

            runDsePodemVariantsBtn.disabled = true;
            status.textContent = dseMode.iterative
                ? `Running DSE #2 (${dseMode.iterations} iterations) on ${selectedNetlists.length} netlist(s)...`
                : `Running DSE #2 on ${selectedNetlists.length} netlist(s)...`;
            status.classList.add('running');
            status.classList.remove('error');
            focusOutputPanel('dse2');
            dseResultsPodemVariants.innerHTML = '';

            try {
                const endpoint = dseMode.iterative ? '/api/dse-podem-variants-iterative' : '/api/dse-podem-variants';
                const requestBody = {
                    netlists: selectedNetlists,
                    metrics: selectedMetrics,
                    ...(dseMode.iterative ? { iterations: dseMode.iterations } : {}),
                };

                const resp = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });

                if (!resp.ok) {
                    throw new Error('Server error: ' + resp.status);
                }

                const data = await resp.json();
                if (data.error) {
                    status.textContent = 'DSE #2 error: ' + data.error;
                    status.classList.add('error');
                    dseResultsPodemVariants.innerHTML = '<div class="empty">' + data.error + '</div>';
                    return;
                }

                status.textContent = `DSE #2 complete: ${(data.comparisons || []).length} netlist comparison(s).`;
                status.classList.remove('running', 'error');
                status.classList.add('success');
                renderDseResults(data.comparisons || [], selectedMetrics, dseResultsPodemVariants, 'DSE #2', 'podem_variants', dseMode.iterative);
            } catch (err) {
                status.textContent = 'DSE #2 failed: ' + err.message;
                status.classList.add('error');
                dseResultsPodemVariants.innerHTML = '<div class="empty">' + err.message + '</div>';
            } finally {
                runDsePodemVariantsBtn.disabled = false;
            }
        }

        async function runDseDVariants() {
            const selectedNetlists = getSelectedNetlists();
            if (selectedNetlists.length === 0) {
                status.textContent = 'Please select at least one netlist for DSE #3.';
                status.classList.add('error');
                return;
            }

            const dseMode = getDseExecutionSettings();
            if (!dseMode) return;

            const selectedMetrics = getSelectedMetrics();
            if (selectedMetrics.length === 0) {
                status.textContent = 'Select at least one metric for DSE #3.';
                status.classList.add('error');
                return;
            }

            runDseDVariantsBtn.disabled = true;
            status.textContent = dseMode.iterative
                ? `Running DSE #3 (${dseMode.iterations} iterations) on ${selectedNetlists.length} netlist(s)...`
                : `Running DSE #3 on ${selectedNetlists.length} netlist(s)...`;
            status.classList.add('running');
            status.classList.remove('error');
            focusOutputPanel('dse3');
            dseResultsDVariants.innerHTML = '';

            try {
                const endpoint = dseMode.iterative ? '/api/dse-d-variants-iterative' : '/api/dse-d-variants';
                const requestBody = {
                    netlists: selectedNetlists,
                    metrics: selectedMetrics,
                    ...(dseMode.iterative ? { iterations: dseMode.iterations } : {}),
                };

                const resp = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });

                if (!resp.ok) {
                    throw new Error('Server error: ' + resp.status);
                }

                const data = await resp.json();
                if (data.error) {
                    status.textContent = 'DSE #3 error: ' + data.error;
                    status.classList.add('error');
                    dseResultsDVariants.innerHTML = '<div class="empty">' + data.error + '</div>';
                    return;
                }

                status.textContent = `DSE #3 complete: ${(data.comparisons || []).length} netlist comparison(s).`;
                status.classList.remove('running', 'error');
                status.classList.add('success');
                renderDseResults(data.comparisons || [], selectedMetrics, dseResultsDVariants, 'DSE #3', 'd_variants', dseMode.iterative);
            } catch (err) {
                status.textContent = 'DSE #3 failed: ' + err.message;
                status.classList.add('error');
                dseResultsDVariants.innerHTML = '<div class="empty">' + err.message + '</div>';
            } finally {
                runDseDVariantsBtn.disabled = false;
            }
        }

        async function runDseSimKernels() {
            const selectedNetlists = getSelectedNetlists();
            if (selectedNetlists.length === 0) {
                status.textContent = 'Please select at least one netlist for DSE #4.';
                status.classList.add('error');
                return;
            }

            const dseMode = { iterative: true, iterations: 3 };

            const selectedMetrics = getSelectedMetrics();
            const dse4Metrics = selectedMetrics.filter(m => m === 'time' || m === 'memory');
            if (dse4Metrics.length === 0) {
                status.textContent = 'DSE #4 supports Time and Peak Memory metrics only. Select at least one.';
                status.classList.add('error');
                return;
            }

            runDseSimKernelsBtn.disabled = true;
            status.textContent = `Running DSE #4 (${dseMode.iterations} iterations) on ${selectedNetlists.length} netlist(s)...`;
            status.classList.add('running');
            status.classList.remove('error');
            focusOutputPanel('dse4');
            dseResultsSimKernels.innerHTML = '';

            try {
                const endpoint = '/api/dse-sim-kernels-iterative';
                const requestBody = {
                    netlists: selectedNetlists,
                    metrics: dse4Metrics,
                    iterations: dseMode.iterations,
                };

                const resp = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });

                if (!resp.ok) {
                    throw new Error('Server error: ' + resp.status);
                }

                const data = await resp.json();
                if (data.error) {
                    status.textContent = 'DSE #4 error: ' + data.error;
                    status.classList.add('error');
                    dseResultsSimKernels.innerHTML = '<div class="empty">' + data.error + '</div>';
                    return;
                }

                status.textContent = `DSE #4 complete: ${(data.comparisons || []).length} netlist comparison(s).`;
                status.classList.remove('running', 'error');
                status.classList.add('success');
                renderDseResults(data.comparisons || [], dse4Metrics, dseResultsSimKernels, 'DSE #4', 'sim_kernels', dseMode.iterative);
            } catch (err) {
                status.textContent = 'DSE #4 failed: ' + err.message;
                status.classList.add('error');
                dseResultsSimKernels.innerHTML = '<div class="empty">' + err.message + '</div>';
            } finally {
                runDseSimKernelsBtn.disabled = false;
            }
        }

        async function runDseFillVariants() {
            const selectedNetlists = getSelectedNetlists();
            if (selectedNetlists.length === 0) {
                status.textContent = 'Please select at least one netlist for DSE #5.';
                status.classList.add('error');
                return;
            }

            const dseMode = getDseExecutionSettings();
            if (!dseMode) return;

            const fillMetrics = ['test_vectors', 'toggle_count', 'peak_switching', 'runtime_overhead'];

            runDseFillVariantsBtn.disabled = true;
            status.textContent = dseMode.iterative
                ? `Running DSE #5 (${dseMode.iterations} iterations) on ${selectedNetlists.length} netlist(s)...`
                : `Running DSE #5 on ${selectedNetlists.length} netlist(s)...`;
            status.classList.add('running');
            status.classList.remove('error');
            focusOutputPanel('dse5');
            dseResultsFillVariants.innerHTML = '';

            try {
                const endpoint = dseMode.iterative ? '/api/dse-fill-variants-iterative' : '/api/dse-fill-variants';
                const resp = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        netlists: selectedNetlists,
                        metrics: fillMetrics,
                        ...(dseMode.iterative ? { iterations: dseMode.iterations } : {}),
                    })
                });

                if (!resp.ok) {
                    throw new Error('Server error: ' + resp.status);
                }

                const data = await resp.json();
                if (data.error) {
                    status.textContent = 'DSE #5 error: ' + data.error;
                    status.classList.add('error');
                    dseResultsFillVariants.innerHTML = '<div class="empty">' + data.error + '</div>';
                    return;
                }

                status.textContent = `DSE #5 complete: ${(data.comparisons || []).length} netlist comparison(s).`;
                status.classList.remove('running', 'error');
                status.classList.add('success');
                renderDseResults(data.comparisons || [], fillMetrics, dseResultsFillVariants, 'DSE #5', 'fill_variants', dseMode.iterative);
            } catch (err) {
                status.textContent = 'DSE #5 failed: ' + err.message;
                status.classList.add('error');
                dseResultsFillVariants.innerHTML = '<div class="empty">' + err.message + '</div>';
            } finally {
                runDseFillVariantsBtn.disabled = false;
            }
        }

        function formatVectorLine(vec, piOrder) {
            const order = (piOrder && piOrder.length) ? piOrder : Object.keys(vec || {}).sort();
            if (!order.length) return 'No vector values';
            return order.map(pi => `${pi}=${(vec || {})[pi] ?? 'X'}`).join(', ');
        }

        function renderVectorSummary(summary, title) {
            const s = summary || { vector_count: 0, pi_order: [], unique_vector_list: [] };
            const vectors = s.unique_vector_list || [];
            const lines = vectors.length
                ? vectors.map(v => `<div class="vector-item">${formatVectorLine(v, s.pi_order || [])}</div>`).join('')
                : '<div class="vector-item">No detected vectors.</div>';

            return `
                <div class="vector-summary">
                    <h4>${title}</h4>
                    <div style="margin-bottom: 8px; font-size: 13px; color: #365274;">Count: <strong>${s.vector_count || 0}</strong></div>
                    <div class="vector-list">${lines}</div>
                </div>
            `;
        }

        function renderDetectedFaultSummary(items, title) {
            const list = items || [];
            const inner = list.length
                ? list.map(item => `<div class="fault-item">${item}</div>`).join('')
                : '<div class="fault-item">No detected faults.</div>';

            return `
                <details style="padding: 0 14px 14px;">
                    <summary>${title} (${list.length})</summary>
                    <div class="faults">${inner}</div>
                </details>
            `;
        }

        function renderFaultSummary(items, title, emptyText) {
            const list = items || [];
            const inner = list.length
                ? list.map(item => `<div class="fault-item">${item}</div>`).join('')
                : `<div class="fault-item">${emptyText}</div>`;

            return `
                <details style="padding: 0 14px 14px;">
                    <summary>${title} (${list.length})</summary>
                    <div class="faults">${inner}</div>
                </details>
            `;
        }

        function renderResults(resultList) {
            if (!resultList || resultList.length === 0) {
                results.innerHTML = '<div class="empty">No results to display.</div>';
                return;
            }

            const chunks = resultList.map((res, idx) => {
                const badgeClass = res.algorithm === 'D'
                    ? 'badge-d'
                    : (res.algorithm === 'PODEM' ? 'badge-podem' : 'badge-run');
                const statHtml = Object.entries(res.stats || {})
                    .map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`)
                    .join('');
                const faults = res.faults || [];
                const faultsHtml = faults.length
                    ? faults.map(f => `<div class="fault-item">${f}</div>`).join('')
                    : '<div class="fault-item">No per-fault lines.</div>';
                const showAdvancedSections = !res.hide_vector_sections;
                const advancedSectionsHtml = showAdvancedSections
                    ? `${renderVectorSummary(res.final_vector_summary, 'Final Test Vector Set')}${renderDetectedFaultSummary(res.detected_faults || [], 'Detected Per-Fault List')}${renderFaultSummary(res.undetected_faults || [], 'Undetected Faults', 'No undetected faults.')}`
                    : '';
                const detailTitle = res.algorithm === 'BASIC' ? 'Simulation details' : 'Per-fault details';
                const imageOptions = Array.isArray(res.basic_image_options) ? res.basic_image_options : [];
                const selectedImageUrl = (res.basic_image_url || (imageOptions.length ? imageOptions[0].url : null));
                const imageSelectId = `basic-image-select-${idx}`;
                const imageViewId = `basic-image-view-${idx}`;
                const dropdownHtml = imageOptions.length > 1
                    ? `
                        <label style="display:block; margin-bottom:8px; font-size:12px; font-weight:700; color:#365274; text-transform:uppercase; letter-spacing:0.04em;">
                            Image Source
                        </label>
                        <select id="${imageSelectId}" onchange="document.getElementById('${imageViewId}').src=this.value;" style="margin-bottom:8px;">
                            ${imageOptions.map(opt => `<option value="${opt.url}" ${opt.url === selectedImageUrl ? 'selected' : ''}>${opt.label}</option>`).join('')}
                        </select>
                    `
                    : '';
                const basicImageHtml = (res.algorithm === 'BASIC' && selectedImageUrl)
                    ? `
                        <div class="basic-image-panel">
                            <h4 class="basic-image-title">Netlist Image</h4>
                            ${dropdownHtml}
                            <img id="${imageViewId}" class="basic-image" src="${selectedImageUrl}" alt="${res.filename} diagram" loading="lazy" />
                        </div>
                    `
                    : '';

                return `
                    <article class="result-card">
                        <div class="result-head">
                            <strong>${res.filename}</strong>
                            <span class="badge ${badgeClass}">${res.algorithm}</span>
                        </div>
                        <div class="stats">${statHtml}</div>
                        ${basicImageHtml}
                        ${advancedSectionsHtml}
                        <details>
                            <summary>${detailTitle} (${faults.length})</summary>
                            <div class="faults">${faultsHtml}</div>
                        </details>
                    </article>
                `;
            });

            results.innerHTML = chunks.join('');
        }

        function renderDseResults(comparisons, selectedMetrics, targetElement, dseLabel, overlapMode, isIterative) {
            if (!comparisons || comparisons.length === 0) {
                targetElement.innerHTML = '<div class="empty">No DSE comparison data.</div>';
                return;
            }

            const executionModeText = isIterative ? 'Execution Mode: Iterative (averaged)' : 'Execution Mode: Single-pass';

            const metricLabels = {
                coverage: 'Coverage (%)',
                time: 'Time (ms)',
                backtracks: 'Total Backtracks',
                memory: 'Peak Memory (KB)',
                test_vectors: 'Final Pattern Count',
                toggle_count: 'Toggle Count',
                peak_switching: 'Peak Switching / Pattern',
                runtime_overhead: 'Fill Overhead (ms)',
            };

            const cards = comparisons.map((cmp, idx) => {
                const algos = cmp.algorithms || [];

                
                if (isIterative) {
                
                    const headers = algos.map(a => `<th>${a.label}</th>`).join('');
                    const rows = selectedMetrics.map(metric => {
                        const statCells = algos.map(a => {
                            const stats = a.metrics_stats && a.metrics_stats[metric];
                            if (!stats) return '<td>N/A</td>';
                            const avg = stats.avg || 0;
                            const decimals = (metric === 'coverage') ? 2 : (metric === 'test_vectors' || metric === 'backtracks') ? 0 : 1;
                            return `<td style="font-size: 13px; font-weight: 600;">${avg.toFixed(decimals)}</td>`;
                        }).join('');
                        return `<tr><td>${metricLabels[metric] || metric}</td>${statCells}</tr>`;
                    }).join('');

                    const overlap = cmp.fault_overlap || {};
                    let overlapText = `Both detected (avg): ${overlap.both_detected_avg || 0} (min: ${overlap.both_detected_min || 0}, max: ${overlap.both_detected_max || 0})`;
                    if (overlapMode === 'd_variants') {
                        overlapText += `, D-only (avg): ${overlap.d_only_avg || 0}, D_QUICK-only (avg): ${overlap.d_quick_only_avg || 0}`;
                    } else if (overlapMode === 'podem_variants') {
                        overlapText += `, PODEM-only (avg): ${overlap.podem_only_avg || 0}, PODEM_NO_HEUR-only (avg): ${overlap.podem_no_heur_only_avg || 0}`;
                    } else if (overlapMode === 'sim_kernels') {
                        const matches = overlap.po_matches_avg || 0;
                        const total = overlap.po_total || 0;
                        const mismatches = overlap.po_mismatches_avg || 0;
                        overlapText = `PO matches (avg): ${matches.toFixed(1)}/${total}, mismatches (avg): ${mismatches.toFixed(1)}`;
                    } else if (overlapMode === 'fill_variants') {
                        overlapText = `Concrete pattern overlap: 0-fill ∩ 1-fill = ${overlap.zero_one_common || 0}, 0-fill ∩ random = ${overlap.zero_random_common || 0}, 1-fill ∩ random = ${overlap.one_random_common || 0}`;
                    } else {
                        overlapText += `, D-only (avg): ${overlap.d_only_avg || 0}, PODEM-only (avg): ${overlap.podem_only_avg || 0}`;
                    }

                    const chartCanvases = selectedMetrics.map(metric => {
                        const id = `${targetElement.id}_chart_${idx}_${metric}`;
                        return `<div class="dse-chart"><canvas id="${id}" height="120"></canvas></div>`;
                    }).join('');

                    const detailBlocks = algos.map(a => {
                        return `
                            ${renderDetectedFaultSummary(a.detected_faults || [], `${a.label} Detected Per-Fault List`)}
                            ${renderFaultSummary(a.undetected_faults || [], `${a.label} Undetected Faults`, 'No undetected faults.')}
                        `;
                    }).join('');

                    return `
                        <article class="result-card">
                            <div class="result-head">
                                <strong>${cmp.netlist}</strong>
                                <span class="badge badge-run">${dseLabel} (Iterative)</span>
                            </div>
                            <div style="padding: 0 12px 10px 12px; color: #365274; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em;">${executionModeText}</div>
                            <div style="padding: 12px; color: #365274; font-size: 13px;">${overlapText}</div>
                            <div style="padding: 0 12px 12px 12px; overflow-x:auto;">
                                <table class="dse-table">
                                    <thead><tr><th>Metric</th>${headers}</tr></thead>
                                    <tbody>${rows}</tbody>
                                </table>
                            </div>
                            <div class="dse-mini-charts" style="padding: 0 12px 12px 12px;">${chartCanvases}</div>
                            <div style="display:grid; gap:10px; padding: 0 0 8px 0;">${detailBlocks}</div>
                        </article>
                    `;
                } else {
                    
                    const headers = algos.map(a => `<th>${a.label}</th>`).join('');
                    const rows = selectedMetrics.map(metric => {
                        const vals = algos.map(a => {
                            const v = a.metrics[metric];
                            if (v === null || v === undefined) return 'N/A';
                            if (typeof v !== 'number') return String(v);
                            if (metric === 'coverage') return v.toFixed(2);
                            if (metric === 'test_vectors' || metric === 'backtracks') return String(Math.round(v));
                            return v.toFixed(3);
                        }).map(v => `<td>${v}</td>`).join('');
                        return `<tr><td>${metricLabels[metric] || metric}</td>${vals}</tr>`;
                    }).join('');

                    const overlap = cmp.fault_overlap || {};
                    let overlapText = `Both detected: ${overlap.both_detected || 0}`;
                    if (overlapMode === 'd_variants') {
                        overlapText = `${overlapText}, D-only: ${overlap.d_only || 0}, D_QUICK-only: ${overlap.d_quick_only || 0}`;
                    } else if (overlapMode === 'podem_variants') {
                        overlapText = `${overlapText}, PODEM-only: ${overlap.podem_only || 0}, PODEM_NO_HEUR-only: ${overlap.podem_no_heur_only || 0}`;
                    } else if (overlapMode === 'sim_kernels') {
                        const matches = overlap.po_matches || 0;
                        const total = overlap.po_total || 0;
                        const mismatches = overlap.po_mismatches || 0;
                        overlapText = `PO matches: ${matches}/${total}, mismatches: ${mismatches}`;
                    } else if (overlapMode === 'fill_variants') {
                        overlapText = `Concrete pattern overlap: 0-fill ∩ 1-fill = ${overlap.zero_one_common || 0}, 0-fill ∩ random = ${overlap.zero_random_common || 0}, 1-fill ∩ random = ${overlap.one_random_common || 0}`;
                    } else {
                        overlapText = `${overlapText}, D-only: ${overlap.d_only || 0}, PODEM-only: ${overlap.podem_only || 0}`;
                    }

                    const vectorBlocks = algos.map(a => {
                        return `
                            ${renderVectorSummary(a.final_vector_summary, `${a.label} Final Vectors`)}
                            ${renderDetectedFaultSummary(a.detected_faults || [], `${a.label} Detected Per-Fault List`)}
                            ${renderFaultSummary(a.undetected_faults || [], `${a.label} Undetected Faults`, 'No undetected faults.')}
                        `;
                    }).join('');

                    const chartCanvases = selectedMetrics.map(metric => {
                        const id = `${targetElement.id}_chart_${idx}_${metric}`;
                        return `<div class="dse-chart"><canvas id="${id}" height="120"></canvas></div>`;
                    }).join('');

                    return `
                        <article class="result-card">
                            <div class="result-head">
                                <strong>${cmp.netlist}</strong>
                                <span class="badge badge-run">${dseLabel}</span>
                            </div>
                            <div style="padding: 0 12px 10px 12px; color: #365274; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em;">${executionModeText}</div>
                            <div style="padding: 12px; color: #365274; font-size: 13px;">${overlapText}</div>
                            <div style="padding: 0 12px 12px 12px; overflow-x:auto;">
                                <table class="dse-table">
                                    <thead><tr><th>Metric</th>${headers}</tr></thead>
                                    <tbody>${rows}</tbody>
                                </table>
                            </div>
                            <div class="dse-mini-charts" style="padding: 0 12px 12px 12px;">${chartCanvases}</div>
                            <div style="display:grid; gap:10px; padding-bottom: 8px;">${vectorBlocks}</div>
                        </article>
                    `;
                }
            });

            targetElement.innerHTML = cards.join('');

            comparisons.forEach((cmp, idx) => {
                selectedMetrics.forEach(metric => {
                    if (isIterative) {
                        drawDseIterativeChart(`${targetElement.id}_chart_${idx}_${metric}`, cmp, metric);
                    } else {
                        drawDseChart(`${targetElement.id}_chart_${idx}_${metric}`, cmp, metric);
                    }
                });
            });
        }

        function drawDseChart(canvasId, comparison, metric) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const width = canvas.width = canvas.clientWidth;
            const height = canvas.height;
            ctx.clearRect(0, 0, width, height);

            const algos = comparison.algorithms || [];
            if (!algos.length) return;

            const values = algos.map(a => Number(a.metrics[metric] || 0));
            const maxVal = Math.max(...values, 1);
            const barW = Math.max(26, Math.floor((width - 40) / Math.max(values.length, 1) - 10));
            const gap = 10;
            const colors = ['#0f766e', '#b91c1c', '#1d4ed8', '#7c3aed'];
            const metricTitle = {
                coverage: 'Coverage (%)',
                time: 'Time (ms)',
                backtracks: 'Backtracks',
                memory: 'Peak Memory (KB)',
                test_vectors: 'Final Pattern Count',
                toggle_count: 'Toggle Count',
                peak_switching: 'Peak Switching / Pattern',
                runtime_overhead: 'Fill Overhead (ms)',
            };

            ctx.font = '12px Space Grotesk';
            ctx.fillStyle = '#365274';
            ctx.fillText(`Metric: ${metricTitle[metric] || metric}`, 10, 16);

            values.forEach((v, i) => {
                const h = Math.round((v / maxVal) * (height - 58));
                const x = 20 + i * (barW + gap);
                const y = height - 28 - h;
                ctx.fillStyle = colors[i % colors.length];
                ctx.fillRect(x, y, barW, h);
                ctx.fillStyle = '#10243f';
                const valueText = (metric === 'backtracks' || metric === 'test_vectors' || metric === 'toggle_count' || metric === 'peak_switching')
                    ? String(Math.round(v))
                    : String(v.toFixed(metric === 'coverage' ? 2 : metric === 'runtime_overhead' ? 3 : 1));
                ctx.fillText(valueText, x, y - 5);
                ctx.fillText(algos[i].label, x, height - 8);
            });
        }

        function drawDseIterativeChart(canvasId, comparison, metric) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const width = canvas.width = canvas.clientWidth;
            const height = canvas.height;
            ctx.clearRect(0, 0, width, height);

            const algos = comparison.algorithms || [];
            if (!algos.length) return;

            
            const avgValues = algos.map(a => {
                const stats = a.metrics_stats && a.metrics_stats[metric];
                return stats ? stats.avg : 0;
            });
            const maxVal = Math.max(...avgValues, 1);
            const barW = Math.max(26, Math.floor((width - 40) / Math.max(algos.length, 1) - 10));
            const gap = 10;
            const colors = ['#0f766e', '#b91c1c', '#1d4ed8', '#7c3aed'];
            const metricTitle = {
                coverage: 'Coverage (%)',
                time: 'Time (ms)',
                backtracks: 'Backtracks',
                memory: 'Peak Memory (KB)',
                test_vectors: 'Final Pattern Count',
                toggle_count: 'Toggle Count',
                peak_switching: 'Peak Switching / Pattern',
                runtime_overhead: 'Fill Overhead (ms)',
            };

            ctx.font = '12px Space Grotesk';
            ctx.fillStyle = '#365274';
            ctx.fillText(`${metricTitle[metric] || metric} (Iterative Avg)`, 10, 16);

            avgValues.forEach((v, i) => {
                
                const h = Math.round((v / maxVal) * (height - 58));
                const x = 20 + i * (barW + gap);
                const y = height - 28 - h;
                ctx.fillStyle = colors[i % colors.length];
                ctx.fillRect(x, y, barW, h);

                ctx.fillStyle = '#10243f';
                const decimals = metric === 'coverage' ? 2 : (metric === 'test_vectors' || metric === 'backtracks') ? 0 : 1;
                ctx.fillText(v.toFixed(decimals), x, y - 5);
                ctx.fillText(algos[i].label, x, height - 8);
            });
        }

        initOutputCollapsibles();
        initDseExecutionControls();
        loadNetlists();
    
