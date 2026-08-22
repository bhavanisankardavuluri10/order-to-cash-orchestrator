import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import {
  HiOutlineClipboardCheck, HiOutlineCube, HiOutlineDocumentText,
  HiOutlineShieldCheck, HiOutlineLightningBolt, HiOutlineChevronDown,
  HiOutlineDownload, HiOutlineRefresh, HiOutlinePlay, HiOutlineArrowRight,
  HiOutlineExclamation, HiOutlineCheck, HiOutlineX, HiOutlineClock,
  HiOutlineSparkles, HiOutlineStatusOnline, HiOutlineCollection,
  HiOutlineTag, HiOutlineUser
} from 'react-icons/hi';
import { RiRobot2Line } from 'react-icons/ri';
import './App.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
const WS  = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws';

const AGENTS = ['order_validator','inventory_checker','invoice_generator','payment_risk'];
const AGENT_INFO = {
  order_validator:   { name: 'Order Validator',   Icon: HiOutlineClipboardCheck, cls: 'validator' },
  inventory_checker: { name: 'Inventory Checker', Icon: HiOutlineCube,           cls: 'inventory' },
  invoice_generator: { name: 'Invoice Generator', Icon: HiOutlineDocumentText,   cls: 'invoice'   },
  payment_risk:      { name: 'Payment Risk',      Icon: HiOutlineShieldCheck,    cls: 'risk'      },
};

const fmt = (n) => `₹${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

// ─── intent icons mapping ────────────────────────────
const INTENT_ICONS = {
  small_order:   '📦', medium_order:  '🛒', large_order:   '🏭',
  bulk_order:    '🚚', electronics:   '📱', fashion:       '👗',
  accessories:   '⌚', premium:       '💎', budget:        '💸',
  mixed:         '🎲', express_rush:  '⚡', high_value:    '🏆',
};

function App() {
  const [activeTab, setActiveTab]       = useState('process');
  const [intents, setIntents]           = useState([]);
  const [customers, setCustomers]       = useState([]);
  const [inventory, setInventory]       = useState([]);
  const [orders, setOrders]             = useState([]);

  // Order builder state
  const [selectedIntent, setIntent]     = useState('medium_order');
  const [selectedCustomer, setCustomer] = useState('');
  const [nlText, setNlText]             = useState('');

  // Workflow state
  const [processing, setProcessing]     = useState(false);
  const [wsOk, setWsOk]                 = useState(false);
  const [statuses, setStatuses]         = useState({});
  const [results, setResults]           = useState({});
  const [decisions, setDecisions]       = useState([]);
  const [final, setFinal]               = useState(null);
  const [plan, setPlan]                 = useState(null);
  const [expanded, setExpanded]         = useState({});
  const [wires, setWires]               = useState({});
  const [workflowId, setWorkflowId]     = useState(null);
  const [qwenThinking, setQwenThinking] = useState(null);

  const seenDecisions = useRef(new Set());
  const wsRef = useRef(null);

  useEffect(() => {
    fetchAll();
    initWs();
    return () => wsRef.current?.close();
  }, []);

  const fetchAll = async () => {
    try {
      const [invRes, intentRes, custRes, ordRes] = await Promise.all([
        axios.get(`${API}/inventory`),
        axios.get(`${API}/orders/intents`),
        axios.get(`${API}/customers`),
        axios.get(`${API}/orders`),
      ]);
      setInventory(invRes.data);
      setIntents(intentRes.data);
      setCustomers(custRes.data);
      setOrders(ordRes.data);
      // Set default customer to first one
      if (custRes.data.length > 0 && !selectedCustomer) {
        setCustomer(custRes.data[0]._id);
      }
    } catch (e) { console.error('fetchAll', e); }
  };

  const initWs = () => {
    const ws = new WebSocket(WS);
    ws.onopen  = () => setWsOk(true);
    ws.onclose = () => { setWsOk(false); setTimeout(initWs, 3000); };
    ws.onmessage = (e) => onWs(JSON.parse(e.data));
    wsRef.current = ws;
  };

  const onWs = useCallback((msg) => {
    const { type, data } = msg;
    if (type === 'workflow_started')  { setWorkflowId(data.workflow_id); }
    if (type === 'qwen_thinking')     { setQwenThinking(data); }
    if (type === 'agent_started')     { setStatuses(p => ({ ...p, [data.agent]: 'working' })); }
    if (type === 'agent_completed') {
      const a = data.agent, res = data.response;
      const pl = res?.payload || {}, mt = res?.metadata || {};
      let s = 'done';
      if (res?.message_type === 'error' || pl.status === 'invalid') s = 'fail';
      else if (pl.status === 'partial')      s = 'warn';
      else if (pl.status === 'insufficient') s = 'fail';
      setStatuses(p => ({ ...p, [a]: s }));
      setResults(p => ({ ...p, [a]: { payload: pl, meta: mt } }));
      setExpanded(p => ({ ...p, [a]: true }));
    }
    if (type === 'routing_decision') {
      const key = `${data.decision}-${data.reasoning}`;
      if (seenDecisions.current.has(key)) return;
      seenDecisions.current.add(key);
      setDecisions(p => [...p, data]);
      if (data.decision === 'PROCEED_PARALLEL')    setWires(p => ({ ...p, 0: true }));
      if (data.decision === 'PROCEED_TO_INVOICE' || data.decision === 'PARTIAL_FULFILL') setWires(p => ({ ...p, 1: true }));
      if (data.decision === 'PROCEED_TO_RISK')     setWires(p => ({ ...p, 2: true }));
    }
    if (type === 'workflow_completed') { setQwenThinking(null); }
  }, []);

  const reset = () => {
    setStatuses({}); setResults({}); setDecisions([]);
    setFinal(null); setPlan(null); setExpanded({}); setWires({});
    setWorkflowId(null); setQwenThinking(null);
    seenDecisions.current.clear();
  };

  const submitIntent = async () => {
    if (!selectedCustomer) return;
    reset(); setProcessing(true);
    try {
      const r = await axios.post(`${API}/orders/intent`, {
        intent: selectedIntent,
        customer_id: selectedCustomer,
      }, { timeout: 120000 });
      setFinal(r.data);
      if (r.data.plan) setPlan(r.data.plan);
      fetchAll();
    } catch (e) { setFinal({ status: 'error', errors: e.message }); }
    finally { setProcessing(false); }
  };

  const submitNL = async () => {
    if (!nlText.trim()) return;
    reset(); setProcessing(true);
    try {
      const r = await axios.post(`${API}/orders/natural`, { text: nlText }, { timeout: 120000 });
      setFinal(r.data);
      fetchAll();
    } catch (e) { setFinal({ status: 'error', errors: e.message }); }
    finally { setProcessing(false); }
  };

  const resetAll = async () => { await axios.post(`${API}/reset-inventory`); reset(); fetchAll(); };

  const toggle = (a) => setExpanded(p => ({ ...p, [a]: !p[a] }));

  const pipeStatus = (a) => statuses[a] || 'idle';
  const pipeCircleCls = (s) => {
    if (s === 'working') return 'working';
    if (s === 'done')    return 'done';
    if (s === 'fail')    return 'fail';
    if (s === 'warn')    return 'warn';
    return 'idle';
  };

  const orchCls = (d) => {
    if (d === 'BACKORDER')      return 'back';
    if (d === 'PARTIAL_FULFILL') return 'part';
    if (d === 'REJECT')          return 'stop';
    if (d === 'COMPLETE')        return 'end';
    return 'go';
  };

  const finalLabel = (s) => ({
    completed:         'Order Completed Successfully',
    partial_fulfilled: 'Partially Fulfilled — Backorder Created',
    backorder_created: 'Backorder Created — Insufficient Stock',
    rejected:          'Order Rejected',
    error:             'Error Processing Order',
  }[s] || s);

  const selectedIntentObj = intents.find(i => i.id === selectedIntent);
  const selectedCustObj   = customers.find(c => c._id === selectedCustomer);

  // ─── PDF Download ──────────────────────────────────────
  const downloadInvoice = () => {
    if (!final?.invoice) return;
    const inv = final.invoice, risk = final.risk_assessment || {};
    const doc = new jsPDF();

    doc.setFontSize(18); doc.setFont('helvetica', 'bold');
    doc.text('ORDER-TO-CASH INVOICE', 14, 22);
    doc.setFontSize(9); doc.setFont('helvetica', 'normal');
    doc.setTextColor(120);
    doc.text('Generated by Multi-Agent Orchestrator v2.0 (Shared Memory Bus)', 14, 28);
    doc.setDrawColor(200); doc.line(14, 32, 196, 32);

    if (plan) {
      doc.setTextColor(80); doc.setFontSize(8);
      doc.text(`Intent: ${plan.intent_label}`, 14, 38);
    }

    doc.setTextColor(60); doc.setFontSize(10); doc.setFont('helvetica', 'bold');
    doc.text('ORDER DETAILS', 14, 46);
    doc.setFont('helvetica', 'normal'); doc.setFontSize(9); doc.setTextColor(80);
    [
      ['Invoice #', inv.invoice_number],
      ['Workflow ID', workflowId || inv.order_id],
      ['Customer', `${inv.customer_name || ''} (${inv.customer_id})`],
      ['Date', inv.date?.split('T')[0] || 'N/A'],
    ].forEach(([k, v], i) => {
      doc.text(`${k}:`, 14, 54 + i * 6);
      doc.setFont('helvetica', 'bold'); doc.text(String(v), 55, 54 + i * 6);
      doc.setFont('helvetica', 'normal');
    });

    autoTable(doc, {
      startY: 82,
      head: [['Product', 'Qty', 'Unit Price (INR)', 'Line Total (INR)']],
      body: inv.line_items.map(li => [li.product_name, li.quantity, fmt(li.unit_price), fmt(li.line_total)]),
      theme: 'grid', headStyles: { fillColor: [99, 102, 241] }, styles: { fontSize: 9 },
    });

    let y = doc.lastAutoTable.finalY + 10;
    doc.setFontSize(9); doc.setTextColor(80);
    doc.text(`Subtotal: ${fmt(inv.subtotal)}`, 140, y);
    doc.text(`CGST (9%): ${fmt(inv.cgst || (inv.tax / 2))}`, 140, y + 6);
    doc.text(`SGST (9%): ${fmt(inv.sgst || (inv.tax / 2))}`, 140, y + 12);
    doc.setFontSize(12); doc.setFont('helvetica', 'bold'); doc.setTextColor(34, 197, 94);
    doc.text(`Grand Total: ${fmt(inv.grand_total)}`, 140, y + 22);

    doc.save(`Invoice_${inv.invoice_number}.pdf`);
  };

  return (
    <>
      {/* HEADER */}
      <header className="app-header">
        <div className="header-left">
          <div className="logo-mark"><HiOutlineLightningBolt /></div>
          <span className="header-title">Order-to-Cash Orchestrator</span>
          <span className="header-badge">Multi-Agent v2.0</span>
        </div>
        <div className="header-right">
          {workflowId && <div className="workflow-id-chip"><HiOutlineClock style={{fontSize:12}}/> {workflowId}</div>}
          <div className="ws-status">
            <div className={`ws-dot ${wsOk ? '' : 'off'}`}></div>
            <span>{wsOk ? 'Connected' : 'Reconnecting…'}</span>
          </div>
        </div>
      </header>

      {/* TABS */}
      <div className="tab-bar">
        <button className={`tab-btn ${activeTab === 'process' ? 'active' : ''}`} onClick={() => setActiveTab('process')}>
          <HiOutlinePlay /> Process Order
        </button>
        <button className={`tab-btn ${activeTab === 'history' ? 'active' : ''}`} onClick={() => { setActiveTab('history'); fetchAll(); }}>
          <HiOutlineCollection /> Order History
          {orders.length > 0 && <span className="tab-count">{orders.length}</span>}
        </button>
      </div>

      <div className="app-body">
        {/* SIDEBAR */}
        <aside className="sidebar">
          {activeTab === 'process' && (
            <>
              {/* Customer Selector */}
              <div className="sidebar-section">
                <span className="section-label"><HiOutlineUser style={{verticalAlign:'middle',marginRight:4}}/> Select Customer</span>
                <select className="scenario-select" value={selectedCustomer} onChange={e => setCustomer(e.target.value)}>
                  {customers.map(c => (
                    <option key={c._id} value={c._id}>
                      {c.name} ({c._id})
                    </option>
                  ))}
                </select>
                {selectedCustObj && (
                  <div className="order-summary-card" style={{marginTop:8}}>
                    <div className="summary-row"><span className="s-label">Tier</span><span className="s-value">{selectedCustObj.risk_profile?.credit_tier}</span></div>
                    <div className="summary-row"><span className="s-label">Credit</span><span className="s-value">{fmt(selectedCustObj.credit_limit)}</span></div>
                    <div className="summary-row"><span className="s-label">Orders</span><span className="s-value">{selectedCustObj.total_orders} total</span></div>
                  </div>
                )}
              </div>

              {/* Intent Selector */}
              <div className="sidebar-section">
                <span className="section-label"><HiOutlineTag style={{verticalAlign:'middle',marginRight:4}}/> Order Intent</span>
                <div className="intent-grid">
                  {intents.map(intent => (
                    <button
                      key={intent.id}
                      className={`intent-card ${selectedIntent === intent.id ? 'selected' : ''}`}
                      onClick={() => setIntent(intent.id)}
                    >
                      <span className="intent-icon">{INTENT_ICONS[intent.id] || '📋'}</span>
                      <span className="intent-label">{intent.label.split(' — ')[0]}</span>
                    </button>
                  ))}
                </div>
                {selectedIntentObj && (
                  <div className="intent-desc-box">
                    <span className="intent-icon">{INTENT_ICONS[selectedIntent] || '📋'}</span>
                    <div>
                      <strong>{selectedIntentObj.label}</strong>
                      <p>{selectedIntentObj.description}</p>
                    </div>
                  </div>
                )}
              </div>

              <div className="sidebar-section">
                <div className="planner-note">
                  <RiRobot2Line style={{fontSize:14,color:'var(--purple-400)'}}/>
                  <span>Qwen reads live inventory and picks the best products and quantities automatically</span>
                </div>
                <button className="btn-submit" onClick={submitIntent} disabled={processing || !selectedCustomer}>
                  {processing
                    ? <><div className="spin"></div>Planning & Processing…</>
                    : <><HiOutlinePlay /> Submit via Orchestrator</>}
                </button>
              </div>

              {/* Natural Language */}
              <div className="sidebar-section">
                <span className="section-label">Or — Natural Language</span>
                <div className="nl-input-group">
                  <textarea
                    className="nl-input"
                    value={nlText}
                    onChange={e => setNlText(e.target.value)}
                    placeholder="e.g. Order 50 Samsung phones for Croma with express shipping..."
                  />
                  <div className="nl-hint">Qwen AI will parse your request into a structured order</div>
                  <button className="btn-nl" onClick={submitNL} disabled={processing || !nlText.trim()}>
                    {processing ? <><div className="spin"></div>Processing…</> : <><RiRobot2Line /> Submit via Qwen AI</>}
                  </button>
                </div>
              </div>

              <div className="sidebar-section">
                <button className="btn-reset" onClick={resetAll}><HiOutlineRefresh style={{fontSize:13}}/> Reset All Data</button>
              </div>
            </>
          )}

          {/* Live Inventory */}
          <div className="sidebar-section">
            <span className="section-label">Live Inventory</span>
            <table className="inv-table">
              <thead><tr><th>Product</th><th>Avail</th></tr></thead>
              <tbody>
                {inventory.map(it => (
                  <tr key={it._id}>
                    <td title={it.name}>{it.name.split('(')[0].trim()}</td>
                    <td><span className={`qty-pill ${it.quantity_available > 200 ? 'high' : it.quantity_available > 0 ? 'low' : 'out'}`}>{it.quantity_available}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </aside>

        {/* MAIN CONTENT */}
        {activeTab === 'process' ? (
          <main className="content">
            {/* Pipeline */}
            <div className="pipeline-strip">
              <div className="pipe-node">
                <div className="pipe-circle orchestrator"><HiOutlineLightningBolt /></div>
                <span className="pipe-name">Orchestrator</span>
              </div>
              <div className={`pipe-wire ${processing || Object.keys(statuses).length ? 'active' : ''}`}></div>
              {AGENTS.map((a, i) => {
                const s = pipeStatus(a), info = AGENT_INFO[a];
                return (
                  <React.Fragment key={a}>
                    <div className="pipe-node">
                      <div className={`pipe-circle ${pipeCircleCls(s)}`}>
                        <info.Icon />
                        {s === 'done' && <div className="pipe-badge ok"><HiOutlineCheck style={{fontSize:10}}/></div>}
                        {s === 'fail' && <div className="pipe-badge err"><HiOutlineX style={{fontSize:10}}/></div>}
                        {s === 'warn' && <div className="pipe-badge wrn">!</div>}
                      </div>
                      <span className="pipe-name">{info.name}</span>
                    </div>
                    {i < AGENTS.length - 1 && (
                      <div className={`pipe-wire ${wires[i] ? 'lit' : ''} ${s === 'working' ? 'active' : ''}`}></div>
                    )}
                  </React.Fragment>
                );
              })}
            </div>

            {/* Plan reveal box */}
            {plan && (
              <div className="plan-reveal">
                <div className="plan-reveal-header">
                  <RiRobot2Line className="plan-robot"/>
                  <div>
                    <strong>Qwen Planner selected {plan.selected_products?.length || 0} products for intent: {plan.intent_label}</strong>
                    <p>{plan.intent_description}</p>
                  </div>
                </div>
                <div className="plan-products">
                  {(plan.selected_products || []).map((p, i) => (
                    <div className="plan-product-chip" key={i}>
                      <span className="pp-id">{p.id}</span>
                      <span className="pp-name">{p.name}</span>
                      <span className="pp-price">{fmt(p.price)}</span>
                      <span className="pp-cat">{p.category}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Qwen thinking bubble */}
            {qwenThinking && (
              <div className="qwen-thinking">
                <div className="qwen-icon"><RiRobot2Line /></div>
                <div className="qwen-text">
                  <strong>Qwen Orchestrator</strong> — {qwenThinking.detail}
                  <span className="qwen-dots"><span></span><span></span><span></span></span>
                </div>
              </div>
            )}

            {/* Orchestrator decisions */}
            {decisions.map((d, i) => (
              <div className={`orch-msg ${orchCls(d.decision)}`} key={i}>
                <div className="orch-avatar"><RiRobot2Line /></div>
                <span><strong>Orchestrator →</strong> {d.reasoning}</span>
              </div>
            ))}

            {/* Agent cards */}
            {Object.keys(statuses).length > 0 ? (
              <div className="agent-cards">
                {AGENTS.filter(a => statuses[a] && statuses[a] !== 'skip').map((a, idx) => {
                  const s = statuses[a], info = AGENT_INFO[a], r = results[a], open = expanded[a];
                  const chipCls  = s === 'done' ? 'ok' : s === 'fail' ? 'err' : s === 'warn' ? 'wrn' : 'working';
                  const chipText = s === 'done' ? 'Complete' : s === 'fail' ? 'Failed' : s === 'warn' ? 'Partial' : 'Working…';
                  return (
                    <div className="a-card" key={a} style={{animationDelay:`${idx * 0.1}s`}}>
                      <div className="a-card-head" onClick={() => toggle(a)}>
                        <div className="a-card-left">
                          <div className={`a-icon ${info.cls}`}><info.Icon /></div>
                          <span className="a-name">{info.name}</span>
                        </div>
                        <div className="a-card-right">
                          {r?.meta?.execution_time != null && <span className="a-time">{r.meta.execution_time.toFixed(2)}s</span>}
                          <span className={`a-chip ${chipCls}`}>
                            {chipCls === 'ok'      && <HiOutlineCheck />}
                            {chipCls === 'err'     && <HiOutlineX />}
                            {chipCls === 'wrn'     && <HiOutlineExclamation />}
                            {chipCls === 'working' && <HiOutlineStatusOnline />}
                            {chipText}
                          </span>
                          <HiOutlineChevronDown className={`a-expand ${open ? 'open' : ''}`}/>
                        </div>
                      </div>
                      {open && r && <div className="a-card-body"><AgentBody agent={a} result={r}/></div>}
                    </div>
                  );
                })}
              </div>
            ) : !processing && (
              <div className="hero-section">
                <div className="hero-icon-row">
                  <div className="hero-agent-bubble"><HiOutlineClipboardCheck /></div>
                  <div className="hero-agent-bubble"><HiOutlineCube /></div>
                  <div className="hero-agent-bubble"><HiOutlineLightningBolt style={{color:'var(--purple-400)'}}/></div>
                  <div className="hero-agent-bubble"><HiOutlineDocumentText /></div>
                  <div className="hero-agent-bubble"><HiOutlineShieldCheck /></div>
                </div>
                <h2 className="hero-title">Dynamic Multi-Agent Order Processing</h2>
                <p className="hero-subtitle">
                  Select a <strong>customer</strong> and an <strong>intent</strong> — the Qwen Orchestrator reads live inventory
                  and builds the order plan automatically. No hardcoded products. No fixed scenarios.
                  Every order is planned fresh from actual stock.
                </p>
                <div className="hero-flow">
                  <span>🎯 Pick Intent</span><HiOutlineArrowRight className="flow-arrow"/>
                  <span>🧠 Qwen Plans</span><HiOutlineArrowRight className="flow-arrow"/>
                  <span>📋 Validate</span><HiOutlineArrowRight className="flow-arrow"/>
                  <span>🔍 Inventory</span><HiOutlineArrowRight className="flow-arrow"/>
                  <span>🧾 Invoice</span><HiOutlineArrowRight className="flow-arrow"/>
                  <span>🛡️ Risk</span><HiOutlineArrowRight className="flow-arrow"/>
                  <span>✅ Done</span>
                </div>
              </div>
            )}

            {/* Final Result */}
            {final && (
              <>
                <div className={`final-bar ${final.status}`}>
                  <div className="final-left">
                    <div className="final-icon">
                      {final.status === 'completed'         && <HiOutlineCheck style={{fontSize:28,color:'var(--green-400)'}}/>}
                      {final.status === 'partial_fulfilled' && <HiOutlineExclamation style={{fontSize:28,color:'var(--amber-400)'}}/>}
                      {(final.status === 'backorder_created' || final.status === 'rejected' || final.status === 'error') && <HiOutlineX style={{fontSize:28,color:'var(--red-400)'}}/>}
                    </div>
                    <div className="final-text">
                      <h3>{finalLabel(final.status)}</h3>
                      <p>{final.workflow_id}</p>
                    </div>
                  </div>
                </div>

                {(final.invoice || final.risk_assessment) && (
                  <div className="result-grid">
                    {final.invoice && (
                      <div className="result-panel">
                        <h3><HiOutlineDocumentText /> Invoice</h3>
                        {final.invoice.line_items.map((li, i) => (
                          <div className="inv-line" key={i}>
                            <span className="il-name">{li.product_name} × {li.quantity}</span>
                            <span className="il-val">{fmt(li.line_total)}</span>
                          </div>
                        ))}
                        <div className="inv-line"><span className="il-name">Subtotal</span><span className="il-val">{fmt(final.invoice.subtotal)}</span></div>
                        <div className="inv-line"><span className="il-name">CGST (9%)</span><span className="il-val">{fmt(final.invoice.cgst || final.invoice.tax/2)}</span></div>
                        <div className="inv-line"><span className="il-name">SGST (9%)</span><span className="il-val">{fmt(final.invoice.sgst || final.invoice.tax/2)}</span></div>
                        <div className="inv-line grand"><span className="il-name">Grand Total</span><span className="il-val">{fmt(final.invoice.grand_total)}</span></div>
                        <button className="btn-download" onClick={downloadInvoice}>
                          <HiOutlineDownload /> Download PDF Report
                        </button>
                      </div>
                    )}
                    {final.risk_assessment && (
                      <div className="result-panel">
                        <h3><HiOutlineShieldCheck /> Risk Assessment</h3>
                        <div className="risk-track">
                          <div className={`risk-fill ${final.risk_assessment.risk_level}`} style={{width:`${Math.min(final.risk_assessment.risk_score, 100)}%`}}></div>
                        </div>
                        <div className="risk-labels">
                          <span className="rl-score">Score: {final.risk_assessment.risk_score}/100</span>
                          <span className={`rl-level ${final.risk_assessment.risk_level}`}>{final.risk_assessment.risk_level?.toUpperCase()}</span>
                        </div>
                        {(final.risk_assessment.risk_factors || []).map((f, i) => (
                          <span className="risk-tag" key={i}><HiOutlineExclamation /> {f}</span>
                        ))}
                        {final.risk_assessment.requires_approval && (
                          <div className="approval-flag"><HiOutlineExclamation /> Manual Approval Required</div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </main>
        ) : (
          /* ORDER HISTORY TAB */
          <main className="history-content">
            {orders.length === 0 ? (
              <div className="history-empty">
                <HiOutlineCollection />
                <h3>No Orders Yet</h3>
                <p>Submit your first order and it will appear here.</p>
              </div>
            ) : (
              <div className="history-grid">
                {orders.map((o, i) => (
                  <div className="history-card" key={o.workflow_id || o._id || i} style={{animationDelay:`${i * 0.04}s`}}>
                    <div className="history-card-top">
                      <span className="history-wf-id">{(o.workflow_id || o._id || '').slice(0,28)}</span>
                      <span className={`history-status ${o.status}`}>{o.status?.toUpperCase().replace(/_/g,' ')}</span>
                    </div>
                    <div className="history-card-body">
                      <div className="history-stat">
                        <span className="history-stat-label">Invoice</span>
                        <span className="history-stat-value mono">{o.invoice?.invoice_number || '—'}</span>
                      </div>
                      <div className="history-stat">
                        <span className="history-stat-label">Total</span>
                        <span className="history-stat-value" style={{color:o.invoice?'var(--green-400)':'var(--text-muted)'}}>
                          {o.invoice ? fmt(o.invoice.grand_total) : '—'}
                        </span>
                      </div>
                      <div className="history-stat">
                        <span className="history-stat-label">Risk</span>
                        <span className="history-stat-value" style={{color:o.risk_assessment?.risk_level==='low'?'var(--green-400)':o.risk_assessment?.risk_level==='medium'?'var(--amber-400)':'var(--red-400)'}}>
                          {o.risk_assessment ? `${o.risk_assessment.risk_level?.toUpperCase()} (${o.risk_assessment.risk_score})` : '—'}
                        </span>
                      </div>
                      <div className="history-stat">
                        <span className="history-stat-label">Time</span>
                        <span className="history-stat-value mono">{o.elapsed_seconds ? `${o.elapsed_seconds}s` : '—'}</span>
                      </div>
                    </div>
                    {o.created_at && <div className="history-date">{new Date(o.created_at).toLocaleString('en-IN')}</div>}
                  </div>
                ))}
              </div>
            )}
          </main>
        )}
      </div>
    </>
  );
}

/* AGENT BODY RENDERERS */
function AgentBody({ agent, result }) {
  const p = result.payload;
  if (agent === 'order_validator') {
    if (p.status === 'invalid') {
      return <div className="a-grid full-span"><div className="a-detail full-span"><div className="a-detail-label">Validation Error</div><div className="a-detail-value" style={{color:'var(--red-400)'}}>{p.errors}</div></div></div>;
    }
    const o = p.validated_order || {};
    return (
      <div className="a-grid">
        <div className="a-detail"><div className="a-detail-label">Customer</div><div className="a-detail-value">{o.customer_name}</div></div>
        <div className="a-detail"><div className="a-detail-label">Shipping</div><div className="a-detail-value">{o.shipping_priority}</div></div>
        <div className="a-detail full-span"><div className="a-detail-label">Line Items</div>
          {(o.line_items || []).map((li, i) => (
            <div key={i} style={{display:'flex',justifyContent:'space-between',padding:'4px 0',fontSize:'0.82rem',borderBottom:'1px solid var(--border)'}}>
              <span>{li.product_name}</span>
              <span style={{color:'var(--text-muted)'}}>× {li.quantity} @ {fmt(li.unit_price)}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (agent === 'inventory_checker') {
    return (
      <div className="a-grid">
        <div className="a-detail"><div className="a-detail-label">Status</div><div className="a-detail-value"><span className={`a-chip ${p.status==='fulfilled'?'ok':p.status==='partial'?'wrn':'err'}`}>{p.status?.toUpperCase()}</span></div></div>
        <div className="a-detail"><div className="a-detail-label">Backorders</div><div className="a-detail-value">{(p.backorder_items||[]).length > 0 ? `${p.backorder_items.length} items` : 'None'}</div></div>
        <div className="a-detail full-span"><div className="a-detail-label">Stock Allocation</div>
          {(p.line_items || []).map((li, i) => (
            <div key={i} style={{display:'flex',justifyContent:'space-between',padding:'5px 0',fontSize:'0.82rem',borderBottom:'1px solid var(--border)'}}>
              <span>{li.product_name}</span>
              <span><span style={{color:'var(--green-400)',fontWeight:600}}>{li.fulfillable_quantity}</span><span style={{color:'var(--text-muted)'}}> / {li.requested_quantity}</span>{li.shortfall > 0 && <span style={{color:'var(--red-400)',marginLeft:8}}>−{li.shortfall}</span>}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (agent === 'invoice_generator') {
    const inv = p.invoice || {};
    return (
      <div className="a-grid">
        <div className="a-detail"><div className="a-detail-label">Invoice #</div><div className="a-detail-value mono">{inv.invoice_number}</div></div>
        <div className="a-detail"><div className="a-detail-label">Grand Total</div><div className="a-detail-value" style={{color:'var(--green-400)',fontSize:'1.1rem',fontWeight:700}}>{fmt(inv.grand_total)}</div></div>
        <div className="a-detail"><div className="a-detail-label">GST (18%)</div><div className="a-detail-value">{fmt(inv.tax)}</div></div>
        <div className="a-detail"><div className="a-detail-label">Customer</div><div className="a-detail-value">{inv.customer_name || inv.customer_id}</div></div>
      </div>
    );
  }
  if (agent === 'payment_risk') {
    const r = p.risk_assessment || {};
    return (
      <div className="a-grid">
        <div className="a-detail"><div className="a-detail-label">Risk Score</div><div className="a-detail-value" style={{fontSize:'1.2rem',fontWeight:700,color:r.risk_level==='low'?'var(--green-400)':r.risk_level==='medium'?'var(--amber-400)':'var(--red-400)'}}>{r.risk_score}/100</div></div>
        <div className="a-detail"><div className="a-detail-label">Level</div><div className="a-detail-value"><span className={`a-chip ${r.risk_level==='low'?'ok':r.risk_level==='medium'?'wrn':'err'}`}>{r.risk_level?.toUpperCase()}</span></div></div>
        {r.requires_approval && <div className="a-detail full-span"><div className="approval-flag"><HiOutlineExclamation /> Manual approval required</div></div>}
      </div>
    );
  }
  return null;
}

export default App;
