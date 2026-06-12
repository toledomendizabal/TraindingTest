import React, { useEffect, useRef, useState } from 'react';
import { createChart } from 'lightweight-charts';
import { api } from '../services/api';

const ChartPage = () => {
    const chartContainerRef = useRef();
    const chartRef = useRef();
    const candleSeriesRef = useRef();
    const ema50SeriesRef = useRef();
    const ema200SeriesRef = useRef();
    const priceLineRefsRef = useRef([]);
    const [asset, setAsset] = useState('XAUUSD');
    const [chartInterval, setChartInterval] = useState('5m');
    const [loading, setLoading] = useState(true);
    const [assets] = useState(['XAUUSD', 'EURUSD', 'GBPUSD', 'GER40Cash', 'US30Cash', 'US100Cash']);

    // Initialize Chart (only once)
    useEffect(() => {
        if (!chartContainerRef.current || chartRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: {
                backgroundColor: '#111827',
                textColor: '#d1d5db',
            },
            grid: {
                vertLines: { color: '#1f2937' },
                horzLines: { color: '#1f2937' },
            },
            crosshair: { mode: 0 },
            priceScale: { borderColor: '#374151' },
            timeScale: {
                borderColor: '#374151',
                timeVisible: true,
                secondsVisible: false,
            },
        });

        // Candlestick Series
        const candlestickSeries = chart.addCandlestickSeries({
            upColor: '#22c55e',
            downColor: '#ef4444',
            borderVisible: false,
            wickUpColor: '#22c55e',
            wickDownColor: '#ef4444',
        });

        // EMA 50 Series (Blue)
        const ema50Series = chart.addLineSeries({
            color: '#3b82f6',
            lineWidth: 2,
            title: 'EMA 50',
        });

        // EMA 200 Series (Orange)
        const ema200Series = chart.addLineSeries({
            color: '#f97316',
            lineWidth: 2,
            title: 'EMA 200',
        });

        chartRef.current = chart;
        candleSeriesRef.current = candlestickSeries;
        ema50SeriesRef.current = ema50Series;
        ema200SeriesRef.current = ema200Series;
        priceLineRefsRef.current = [];

        const handleResize = () => {
            if (chartContainerRef.current) {
                chart.applyOptions({ width: chartContainerRef.current.clientWidth });
            }
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
        };
    }, []);

    // Fetch and update data
    useEffect(() => {
        if (!chartRef.current || !candleSeriesRef.current) return;

        const fetchData = async () => {
            setLoading(true);
            try {
                // Fetch Candles
                const response = await api.get(`/charts/candles/${asset}?interval=${chartInterval}`);
                if (response.data && response.data.candles) {
                    candleSeriesRef.current.setData(response.data.candles);
                }

                // Fetch EMA data
                if (response.data && response.data.ema50) {
                    ema50SeriesRef.current.setData(response.data.ema50);
                }
                if (response.data && response.data.ema200) {
                    ema200SeriesRef.current.setData(response.data.ema200);
                }

                // Fetch Markers (Signals) - WITHOUT price lines to avoid memory leak
                const markersResponse = await api.get(`/charts/markers/${asset}`);
                if (markersResponse.data && Array.isArray(markersResponse.data)) {
                    const markers = markersResponse.data.filter(m => m.type !== 'price_line');
                    candleSeriesRef.current.setMarkers(markers);

                    // Clear old price lines
                    priceLineRefsRef.current.forEach(line => {
                        try {
                            candleSeriesRef.current.removePriceLine(line);
                        } catch (e) {
                            // Silently ignore
                        }
                    });
                    priceLineRefsRef.current = [];

                    // Add new price lines (limit to 10 to avoid memory issues)
                    const priceLines = markersResponse.data.filter(m => m.type === 'price_line').slice(0, 10);
                    priceLines.forEach(line => {
                        try {
                            const priceLine = candleSeriesRef.current.createPriceLine({
                                price: line.price,
                                color: line.color,
                                lineWidth: 2,
                                lineStyle: 2, // Dashed
                                axisLabelVisible: true,
                                title: line.title,
                            });
                            priceLineRefsRef.current.push(priceLine);
                        } catch (e) {
                            console.warn('Error creating price line:', e);
                        }
                    });
                }

                // Auto-scale the chart
                if (chartRef.current) {
                    chartRef.current.timeScale().fitContent();
                }
            } catch (error) {
                console.error('Error fetching chart data:', error);
            }
            setLoading(false);
        };

        fetchData();
        const intervalId = window.setInterval(fetchData, 30000); // Refresh every 30s

        return () => window.clearInterval(intervalId);
    }, [asset, chartInterval]);

    return (
        <div className="p-6 bg-gray-900 min-h-screen text-white">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold">Gráficos en Tiempo Real (MT5 Data)</h1>
                <div className="flex space-x-4">
                    <select 
                        value={asset} 
                        onChange={(e) => setAsset(e.target.value)}
                        className="bg-gray-800 border border-gray-700 rounded px-3 py-2 outline-none focus:ring-2 focus:ring-blue-500"
                    >
                        {assets.map(a => <option key={a} value={a}>{a}</option>)}
                    </select>
                    <select 
                        value={chartInterval} 
                        onChange={(e) => setChartInterval(e.target.value)}
                        className="bg-gray-800 border border-gray-700 rounded px-3 py-2 outline-none focus:ring-2 focus:ring-blue-500"
                    >
                        <option value="1m">1m</option>
                        <option value="5m">5m</option>
                        <option value="15m">15m</option>
                        <option value="1h">1h</option>
                        <option value="1d">1d</option>
                    </select>
                </div>
            </div>

            <div className="bg-gray-800 rounded-lg p-4 shadow-xl border border-gray-700 relative">
                {loading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-gray-900 bg-opacity-50 z-10 rounded-lg">
                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                    </div>
                )}
                <div ref={chartContainerRef} style={{ height: '600px', width: '100%' }} />
            </div>

            <div className="mt-6 grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
                    <h3 className="text-sm font-medium text-gray-400">Fuente de Datos</h3>
                    <p className="text-lg font-bold text-green-500">MetaTrader 5</p>
                </div>
                <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
                    <h3 className="text-sm font-medium text-gray-400">EMA 50</h3>
                    <p className="text-lg font-bold text-blue-500">━━━</p>
                </div>
                <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
                    <h3 className="text-sm font-medium text-gray-400">EMA 200</h3>
                    <p className="text-lg font-bold text-orange-500">━━━</p>
                </div>
                <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
                    <h3 className="text-sm font-medium text-gray-400">Actualización</h3>
                    <p className="text-lg font-bold text-gray-200">Cada 30s</p>
                </div>
            </div>
        </div>
    );
};

export default ChartPage;
