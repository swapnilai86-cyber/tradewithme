import React, { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { createChart } from 'lightweight-charts';
import { useAuth } from '../context/AuthContext';

const StandaloneChart = () => {
    const { symbol } = useParams();
    const { token } = useAuth();
    
    const chartContainerRef = useRef(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [timeframe, setTimeframe] = useState('15m'); // '15m' or '1D'
    
    useEffect(() => {
        if (!chartContainerRef.current) return;
        
        let chart = null;
        let candleSeries = null;
        let volumeSeries = null;
        
        const fetchAndRenderData = async () => {
            setLoading(true);
            setError(null);
            
            try {
                const response = await fetch(`/api/charts/${symbol}?tf=${timeframe}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (!response.ok) {
                    throw new Error(`Failed to fetch historical data for ${timeframe}`);
                }
                
                const json = await response.json();
                const data = json.data;
                const sr_levels = json.sr_levels || {};
                
                if (!data || data.length === 0) {
                    throw new Error('No data available for chart');
                }
                
                // Clear any existing chart instance
                if (chartContainerRef.current.innerHTML !== '') {
                    chartContainerRef.current.innerHTML = '';
                }
                
                // Initialize Chart
                chart = createChart(chartContainerRef.current, {
                    layout: {
                        background: { type: 'solid', color: 'transparent' },
                        textColor: '#d1d5db',
                    },
                    grid: {
                        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
                        horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
                    },
                    width: chartContainerRef.current.clientWidth,
                    height: chartContainerRef.current.clientHeight,
                    timeScale: {
                        timeVisible: timeframe === '15m',
                        secondsVisible: false,
                    },
                    crosshair: {
                        mode: 1, // Normal crosshair
                    }
                });
                
                // Add Candlestick Series
                candleSeries = chart.addCandlestickSeries({
                    upColor: '#26a69a',
                    downColor: '#ef5350',
                    borderVisible: false,
                    wickUpColor: '#26a69a',
                    wickDownColor: '#ef5350',
                });
                
                // Add Volume Series
                volumeSeries = chart.addHistogramSeries({
                    color: '#26a69a',
                    priceFormat: { type: 'volume' },
                    priceScaleId: '', // set as an overlay
                    scaleMargins: {
                        top: 0.8, // highest point of volume will be at 80% of chart height
                        bottom: 0,
                    },
                });
                
                // Map data for lightweight-charts
                const cData = data.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close }));
                const vData = data.map(d => ({ time: d.time, value: d.value, color: d.color }));
                
                candleSeries.setData(cData);
                volumeSeries.setData(vData);
                
                // Add Static Horizontal Support/Resistance Lines
                if (sr_levels) {
                    const drawPriceLine = (price, title, color) => {
                        if (price && price > 0) {
                            candleSeries.createPriceLine({
                                price: price,
                                color: color,
                                lineWidth: 2,
                                lineStyle: 2, // Dashed line
                                axisLabelVisible: true,
                                title: title,
                            });
                        }
                    };
                    
                    // Red for resistance, Green for support
                    drawPriceLine(sr_levels.R3_200, 'R3 (200P)', 'rgba(239, 68, 68, 0.8)');
                    drawPriceLine(sr_levels.R2_60, 'R2 (60P)', 'rgba(239, 68, 68, 0.6)');
                    drawPriceLine(sr_levels.R1_20, 'R1 (20P)', 'rgba(239, 68, 68, 0.4)');
                    
                    drawPriceLine(sr_levels.S3_200, 'S3 (200P)', 'rgba(34, 197, 94, 0.8)');
                    drawPriceLine(sr_levels.S2_60, 'S2 (60P)', 'rgba(34, 197, 94, 0.6)');
                    drawPriceLine(sr_levels.S1_20, 'S1 (20P)', 'rgba(34, 197, 94, 0.4)');
                }
                
                chart.timeScale().fitContent();
                
                // --- Legend Logic ---
                const legend = document.getElementById('standalone-chart-legend');
                const updateLegend = (param) => {
                    if (!param || !param.time || param.point.x < 0 || param.point.x > chartContainerRef.current.clientWidth || param.point.y < 0 || param.point.y > chartContainerRef.current.clientHeight) {
                        // Display last candle when not hovering
                        const lastCandle = cData[cData.length - 1];
                        if (lastCandle && legend) {
                            legend.innerHTML = `
                                <div style="font-size: 1.5rem; font-weight: bold; color: var(--text-primary); margin-bottom: 4px;">
                                    ${symbol} <span style="font-size: 1rem; font-weight: normal; color: var(--text-secondary)">${timeframe === '15m' ? '15m' : 'Daily'}</span>
                                </div>
                                <div style="font-size: 1rem; color: var(--text-primary);">
                                    <span style="margin-right: 4px; color: var(--text-secondary);">O</span><span style="margin-right: 12px; font-weight: 500">${lastCandle.open.toFixed(2)}</span>
                                    <span style="margin-right: 4px; color: var(--text-secondary);">H</span><span style="margin-right: 12px; font-weight: 500">${lastCandle.high.toFixed(2)}</span>
                                    <span style="margin-right: 4px; color: var(--text-secondary);">L</span><span style="margin-right: 12px; font-weight: 500">${lastCandle.low.toFixed(2)}</span>
                                    <span style="margin-right: 4px; color: var(--text-secondary);">C</span><span style="font-weight: 500; color: ${lastCandle.close >= lastCandle.open ? 'var(--accent-green)' : 'var(--accent-red)'}">${lastCandle.close.toFixed(2)}</span>
                                </div>
                            `;
                        }
                        return;
                    }

                    const candle = param.seriesData.get(candleSeries);
                    if (candle && legend) {
                        legend.innerHTML = `
                            <div style="font-size: 1.5rem; font-weight: bold; color: var(--text-primary); margin-bottom: 4px;">
                                ${symbol} <span style="font-size: 1rem; font-weight: normal; color: var(--text-secondary)">${timeframe === '15m' ? '15m' : 'Daily'}</span>
                            </div>
                            <div style="font-size: 1rem; color: var(--text-primary);">
                                <span style="margin-right: 4px; color: var(--text-secondary);">O</span><span style="margin-right: 12px; font-weight: 500">${candle.open.toFixed(2)}</span>
                                <span style="margin-right: 4px; color: var(--text-secondary);">H</span><span style="margin-right: 12px; font-weight: 500">${candle.high.toFixed(2)}</span>
                                <span style="margin-right: 4px; color: var(--text-secondary);">L</span><span style="margin-right: 12px; font-weight: 500">${candle.low.toFixed(2)}</span>
                                <span style="margin-right: 4px; color: var(--text-secondary);">C</span><span style="font-weight: 500; color: ${candle.close >= candle.open ? 'var(--accent-green)' : 'var(--accent-red)'}">${candle.close.toFixed(2)}</span>
                            </div>
                        `;
                    }
                };
                
                updateLegend(null);
                chart.subscribeCrosshairMove(updateLegend);
                // ---------------------

                setLoading(false);
                
            } catch (err) {
                console.error(err);
                setError(err.message);
                setLoading(false);
            }
        };
        
        fetchAndRenderData();
        
        const handleResize = () => {
            if (chart && chartContainerRef.current) {
                chart.applyOptions({ 
                    width: chartContainerRef.current.clientWidth,
                    height: chartContainerRef.current.clientHeight
                });
            }
        };
        window.addEventListener('resize', handleResize);
        
        return () => {
            window.removeEventListener('resize', handleResize);
            if (chart) {
                chart.remove();
            }
        };
    }, [symbol, token, timeframe]);
    
    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw', backgroundColor: 'var(--bg-color)' }}>
            
            {/* Toolbar */}
            <div style={{
                padding: '1rem 2rem',
                backgroundColor: 'var(--panel-bg)',
                borderBottom: '1px solid var(--border-color)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                backdropFilter: 'var(--glass-blur)'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <h2 style={{ margin: 0, color: 'var(--text-primary)' }}>{symbol}</h2>
                    
                    <div style={{ display: 'flex', gap: '0.5rem', background: 'rgba(0,0,0,0.2)', padding: '4px', borderRadius: '8px' }}>
                        <button 
                            onClick={() => setTimeframe('15m')}
                            style={{
                                padding: '6px 16px',
                                border: 'none',
                                borderRadius: '6px',
                                cursor: 'pointer',
                                fontWeight: '600',
                                background: timeframe === '15m' ? 'var(--accent-blue)' : 'transparent',
                                color: timeframe === '15m' ? 'white' : 'var(--text-secondary)',
                                transition: 'all 0.2s ease'
                            }}
                        >
                            15m
                        </button>
                        <button 
                            onClick={() => setTimeframe('1D')}
                            style={{
                                padding: '6px 16px',
                                border: 'none',
                                borderRadius: '6px',
                                cursor: 'pointer',
                                fontWeight: '600',
                                background: timeframe === '1D' ? 'var(--accent-blue)' : 'transparent',
                                color: timeframe === '1D' ? 'white' : 'var(--text-secondary)',
                                transition: 'all 0.2s ease'
                            }}
                        >
                            Daily
                        </button>
                    </div>
                </div>
            </div>

            {/* Chart Area */}
            <div style={{ flex: 1, position: 'relative' }}>
                {loading && (
                    <div style={{ position: 'absolute', inset: 0, display: 'flex', justifyContent: 'center', alignItems: 'center', color: 'var(--text-secondary)', zIndex: 10 }}>
                        Loading chart data...
                    </div>
                )}
                {error && (
                    <div style={{ position: 'absolute', inset: 0, display: 'flex', justifyContent: 'center', alignItems: 'center', color: 'var(--accent-red)', zIndex: 10 }}>
                        {error}
                    </div>
                )}
                
                {/* Dynamic Legend Overlay */}
                <div id="standalone-chart-legend" style={{ position: 'absolute', top: 20, left: 24, zIndex: 20, pointerEvents: 'none' }}></div>
                
                <div 
                    ref={chartContainerRef} 
                    style={{ 
                        width: '100%', 
                        height: '100%', 
                        opacity: (loading || error) ? 0 : 1, 
                        transition: 'opacity 0.3s ease' 
                    }}
                />
            </div>
            
        </div>
    );
};

export default StandaloneChart;
