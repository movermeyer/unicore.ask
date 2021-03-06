import os
from mock import patch
from ConfigParser import ConfigParser
from unittest import TestCase

from sqlalchemy.orm import sessionmaker
from alembic import command as alembic_command
from alembic.config import Config

from webtest import TestApp

from unicore.ask.service import main


config_file_path = os.path.join(os.path.dirname(__file__), 'test.ini')


def get_test_settings():
    here = os.path.dirname(__file__)
    config = ConfigParser()
    config.read(config_file_path)
    settings = dict(config.items('app:unicore.ask.service',
                                 vars={'here': here}))
    return (here, config_file_path, settings)


def get_alembic_config(alembic_dir):
    config = Config(os.path.join(alembic_dir, '../../../../alembic.ini'))
    config.set_main_option('script_location', alembic_dir)
    config.set_main_option('pyramid_config_file', config_file_path)
    return config


def make_app(working_dir, config_file_path, settings,
             extra_environ={}):
    app = TestApp(main({
        '__file__': config_file_path,
        'here': working_dir,
    }, **settings), extra_environ=extra_environ)
    return app


class DBTestCase(TestCase):

    def create_model_object(self, model, session=None, **attrs):
        obj = model()
        for key, val in attrs.iteritems():
            setattr(obj, key, val)

        if session is not None:
            session.add(obj)

        return obj

    @classmethod
    def setUpClass(cls):
        # bind sessions to single database connection
        def sessionmaker_in_transaction(bind):
            cls.connection = bind.connect()
            return sessionmaker(bind=cls.connection)

        cls.transaction_context = patch(
            'unicore.ask.service.sessionmaker',
            new=sessionmaker_in_transaction)
        cls.transaction_context.start()

        # set up app
        working_dir, config_file_path, settings = get_test_settings()
        cls.working_dir = working_dir
        cls.config_file_path = config_file_path
        cls.settings = settings
        cls.app = make_app(
            working_dir=working_dir,
            config_file_path=config_file_path,
            settings=settings)
        cls.sessionmaker = cls.app.app.registry.dbmaker

        # migrate the database
        cls.alembic_config = get_alembic_config(
            alembic_dir=os.path.join(working_dir, '../alembic'))
        alembic_command.upgrade(cls.alembic_config, 'head')

    @classmethod
    def tearDownClass(cls):
        alembic_command.downgrade(cls.alembic_config, 'base')
        cls.connection.close()
        cls.transaction_context.stop()

    def setUp(self):
        self.app.reset()
        self.transaction = self.__class__.connection.begin()
        self.db = self.__class__.sessionmaker()

    def tearDown(self):
        self.db.close()
        self.transaction.rollback()
