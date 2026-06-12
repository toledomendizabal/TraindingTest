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
    
    const [selectedAsset, setSelectedAsset] = useState('XAUUSD');
    const [timeframe, setTimeframe] = useState('5m');
    const [isLoading, setIsLoading] = useState(true);
    const [assetList] = useState(['XAUUSD', 'EURUSD', 'GBPUSD', 'GER40Cash', 'US30Cash', 'US100Cash']);

    // Initialize Chart
    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { color: '#111827' },
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

        const candlestickSeries = chart.addCandlestickSeries({
            upColor: '#22c55e',
            downColor: '#ef4444',
            borderVisible: false,
            wickUpColor: '#22c55e',
            wickDownColor: '#ef4444',
        });

        const ema50Series = chart.addLineSeries({
            color: '#3b82f6',
            lineWidth: 2,
            title: 'EMA 50',
        });

        const ema200Series = chart.addLineSeries({
            color: '#f97316',
            lineWidth: 2,
            title: 'EMA 200',
        });

        chartRef.current = chart;
        candleSeriesRef.current = candlestickSeries;
        ema50SeriesRef.current = ema50Series;
        ema200SeriesRef.current = ema200Series;

        const handleResize = () => {
            if (chartContainerRef.current && chartRef.current) {
                chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
            }
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            if (chartRef.current) {
                chartRef.current.remove();
                chartRef.current = null;
            }
        };
    }, []);

    // Data Fetching Logic
    useEffect(() => {
        if (!chartRef.current) return;

        const loadData = async () => {
            setIsLoading(true);
            try {
                // Fetch Candles with explicit timeframe string
                const response = await api.get(`/charts/candles/${selectedAsset}`, {
                    params: { interval: timeframe }
                });

                if (response.data) {
                    if (response.data.candles) candleSeriesRef.current.setData(response.data.candles);
                    if (response.data.ema50) ema50SeriesRef.current.setData(response.data.ema50);
                    if (response.data.ema200) ema200SeriesRef.current.setData(response.data.ema200);
                }

                // Fetch Markers
                const markersRes = await api.get(`/charts/markers/${selectedAsset}`);
                if (markersRes.data && Array.isArray(markersRes.data)) {
                    // Filter markers
                    const visualMarkers = markersRes.data.filter(m => m.type !== 'price_line');
                    candleSeriesRef.current.setMarkers(visualMarkers);

                    // Clear and set price lines
                    priceLineRefsRef.current.forEach(line => {
                        try { candleSeriesRef.current.removePriceLine(line); } catch (e) {}
                    });
                    priceLineRefsRef.current = [];

                    const priceLines = markersRes.data.filter(m => m.type === 'price_line').slice(0, 10);
                    priceLines.forEach(line => {
                        const pl = candleSeriesRef.current.createPriceLine({
                            price: line.price,
                            color: line.color,
                            lineWidth: 2,
                            lineStyle: 2,
                            title: line.title,
                        });
                        priceLineRefsRef.current.push(pl);
                    });
                }
            } catch (err) {
                console.error("Chart data error:", err);
            } finally {
                setIsLoading(false);
            }
        };

        loadData();
        const timer = window.setInterval(loadData, 30000);

        return () => window.clearInterval(timer);
    }, [selectedAsset, timeframe]);

    return (
        <div className="p-6 bg-gray-900 min-h-screen text-white">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold">Gráficos en Tiempo Real (MT5 Data)</h1>
                <div className="flex space-x-4">
                    <select 
                        value={selectedAsset} 
                        onChange={(e) => setSelectedAsset(e.target.value)}
                        className="bg-gray-800 border border-gray-700 rounded px-3 py-2 outline-none"
                    >
                        {assetList.map(a => <option key={a} value={a}>{a}</option>)}
                    </select>
                    <select 
                        value={timeframe} 
                        onChange={(e) => setTimeframe(e.target.value)}
                        className="bg-gray-800 border border-gray-700 rounded px-3 py-2 outline-none"
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
                {isLoading && (
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
