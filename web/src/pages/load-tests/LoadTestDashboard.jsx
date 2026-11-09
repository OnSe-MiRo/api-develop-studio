import { lazy, Suspense } from 'react'
import { RouteLoading } from '../../components/RouteLoading.jsx'

const LoadTestList = lazy(() => import('./LoadTestList.jsx').then(module => ({ default: module.LoadTestList })))
const LoadTestDetail = lazy(() => import('./LoadTestDetail.jsx').then(module => ({ default: module.LoadTestDetail })))
const LoadTestComparison = lazy(() => import('./LoadTestComparison.jsx').then(module => ({ default: module.LoadTestComparison })))

export function LoadTestDashboard({ route, refreshKey }) {
  return <Suspense fallback={<RouteLoading />}>
    {route.tab === 'load-test-compare' ? <LoadTestComparison route={route} refreshKey={refreshKey} /> : route.tab === 'load-test-result' ? <LoadTestDetail route={route} refreshKey={refreshKey} /> : <LoadTestList route={route} refreshKey={refreshKey} />}
  </Suspense>
}
