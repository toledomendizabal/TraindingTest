import React, { useEffect, useRef, useState } from 'react';
import { createChart } from 'lightweight-charts';
import api from '../services/api';

const ChartPage = () => {
    const chartContainerRef = useRef();
    const chartRef = useRef();
    const seriesRef = useRef();
    const [asset, setAsset] = useState('XAUUSD');
    const [interval, setInterval] = useState('5m');
    const [loading, setLoading] = useState(true);
    const [assets, setAssets] = useState(['XAUUSD', 'EURUSD', 'GBPUSD', 'GER40Cash', 'US30Cash', 'US100Cash']);

    useEffect(() => {
        if (!chartContainerRef.current) return;

        // Initialize Chart
        const chart = createChart(chartContainerRef.current, {
            layout: {
                backgroundColor: '#111827',
                textColor: '#d1d5db',
            },
            grid: {
                vertLines: { color: '#1f2937' },
                horzLines: { color: '#1f2937' },
            },
            crosshair: {
                mode: 0,
            },
            priceScale: {
                borderColor: '#374151',
            },
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

        chartRef.current = chart;
        seriesRef.current = candlestickSeries;

        const handleResize = () => {
            chart.applyOptions({ width: chartContainerRef.current.clientWidth });
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
        };
    }, []);

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                // Fetch Candles
                const response = await api.get(`/charts/candles/${asset}?interval=${interval}`);
                if (response.data && response.data.candles) {
                    seriesRef.current.setData(response.data.candles);
                }

                // Fetch Markers (Signals)
                const markersResponse = await api.get(`/charts/markers/${asset}`);
                if (markersResponse.data) {
                    const markers = markersResponse.data.filter(m => m.type !== 'price_line');
                    seriesRef.current.setMarkers(markers);

                    // Add Price Lines for SL/TP
                    const priceLines = markersResponse.data.filter(m => m.type === 'price_line');
                    // Clear existing lines (not directly supported by simple API, but we can manage)
                    // For now, just add them
                    priceLines.forEach(line => {
                        seriesRef.current.createPriceLine({
                            price: line.price,
                            color: line.color,
                            lineWidth: 2,
                            lineStyle: 2, // Dashed
                            axisLabelVisible: true,
                            title: line.title,
                        });
                    });
                }
            } catch (error) {
                console.error('Error fetching chart data:', error);
            }
            setLoading(false);
        };

        fetchData();
        const intervalId = setInterval(fetchData, 30000); // Refresh every 30s

        return () => clearInterval(intervalId);
    }, [asset, interval]);

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
                        value={interval} 
                        onChange={(e) => setInterval(e.target.value)}
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

            <div className="bg-gray-800 rounded-lg p-4 shadow-xl border border-gray-700">
                {loading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-gray-900 bg-opacity-50 z-10">
                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                    </div>
                )}
                <div ref={chartContainerRef} style={{ height: '600px', width: '100%' }} />
            </div>

            <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
                    <h3 className="text-sm font-medium text-gray-400">Fuente de Datos</h3>
                    <p className="text-lg font-bold text-green-500">MetaTrader 5 (Local)</p>
                </div>
                <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
                    <h3 className="text-sm font-medium text-gray-400">Estado de Red</h3>
                    <p className="text-lg font-bold text-blue-500">Conectado (Live)</p>
                </div>
                <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
                    <h3 className="text-sm font-medium text-gray-400">Actualización</h3>
                    <p className="text-lg font-bold text-gray-200">Cada 30 segundos</p>
                </div>
            </div>
        </div>
    );
};

export default ChartPage;
