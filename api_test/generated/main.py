"""Generated router registry. Application setup lives in api_test/main.py."""

from api_test.generated.apis.cases_api import router as CasesApiRouter

from api_test.generated.apis.dashboard_api import router as DashboardApiRouter

from api_test.generated.apis.example_api import router as ExampleApiRouter

from api_test.generated.apis.execution_api import router as ExecutionApiRouter

from api_test.generated.apis.openapi_api import router as OpenapiApiRouter

from api_test.generated.apis.ownership_api import router as OwnershipApiRouter

from api_test.generated.apis.pipelines_api import router as PipelinesApiRouter

from api_test.generated.apis.projects_api import router as ProjectsApiRouter

from api_test.generated.apis.uploads_api import router as UploadsApiRouter


routers = [

    CasesApiRouter,

    DashboardApiRouter,

    ExampleApiRouter,

    ExecutionApiRouter,

    OpenapiApiRouter,

    OwnershipApiRouter,

    PipelinesApiRouter,

    ProjectsApiRouter,

    UploadsApiRouter,

]
