from .schemas import ProjectCreate
from .services import MemoryStore


def seed_demo_projects(store: MemoryStore) -> list:
    seeds = [
        ProjectCreate(name="v5 BD+C Demo Office", location_country="China", location_city="Shanghai", building_type="Office", leed_version="v5", rating_family="BDC", adaptation="NC", target_certification="Gold"),
        ProjectCreate(name="v5 ID+C Demo Fit-out", location_country="China", location_city="Beijing", building_type="Commercial Interiors", leed_version="v5", rating_family="IDC", adaptation="CI", target_certification="Gold"),
        ProjectCreate(name="v4.1 O+M Demo Existing Office", location_country="China", location_city="Shanghai", building_type="Existing Office", leed_version="v4_1", rating_family="OM", adaptation="ExistingBuildings", target_certification="Silver"),
    ]
    return [store.create_project(seed) for seed in seeds]
