#!/usr/bin/env python
"""export3031.py - A script to export all the data from Gluu Server 3.0.x

Usage: python export3031.py

Running this creates a folder named `backup_3031` which contains all the data
needed for migration of Gluu Server to a higher version. This script backs up
the following data:
    1. LDAP data
    2. Configurations of various components installed inside Gluu Server
    3. CA certificates in /etc/certs
    4. Webapp Customization files

This backup folder should be used as the input for the `import___.py` script
of appropriate version to migrate to that version.

Read complete migration procedure at:
    https://www.gluu.org/docs/deployment/upgrading/
"""
import os
import os.path
import sys
import logging
import traceback
import subprocess
import tempfile
import getpass
from ldif import LDIFParser, LDIFWriter, CreateLDIF
from distutils.dir_util import copy_tree
import json
from shutil import copyfile
import os.path


class MyLDIF(LDIFParser):
    def __init__(self, input, output):
        LDIFParser.__init__(self, input)
        self.targetDN = None
        self.targetAttr = None
        self.targetEntry = None
        self.DNs = []
        self.lastDN = None
        self.lastEntry = None
        self.entries = []

    def getResults(self):
        return (self.targetDN, self.targetAttr)

    def getDNs(self):
        return self.DNs

    def getLastEntry(self):
        return self.lastEntry

    def parseAttrTypeandValue(self):
        return LDIFParser._parseAttrTypeandValue(self)

    def handle(self, dn, entry):
        if self.targetDN is None:
            self.targetDN = dn
        self.lastDN = dn
        self.DNs.append(dn)
        self.lastEntry = entry
        self.entries.append(entry)
        if dn.lower().strip() == self.targetDN.lower().strip():
            self.targetEntry = entry
            if self.targetAttr in entry:
                self.targetAttr = entry[self.targetAttr]


SKIP_DN = []

# configure logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(name)s %(message)s',
                    filename='export30.log',
                    filemode='w')
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(levelname)-8s %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)


def doOxTrustChanges(oxTrustPath):
    parser = MyLDIF(open(oxTrustPath, 'rb'), sys.stdout)
    parser.targetAttr = "oxTrustConfApplication"
    atr = parser.parse()
    oxTrustConfApplication = parser.lastEntry['oxTrustConfApplication'][0]
    oxTrustConfApplication = oxTrustConfApplication.replace('seam/resource/', '')
    parser.lastEntry['oxTrustConfApplication'][0] = oxTrustConfApplication
    oxTrustConfApplicationJson = json.loads(oxTrustConfApplication)
    oxTrustConfApplicationJson['ScimProperties'] = json.loads('{"maxCount": "200"}')

    del oxTrustConfApplicationJson['loggingLevel']
    del oxTrustConfApplicationJson['oxIncommonFlag']
    del oxTrustConfApplicationJson['recaptchaSiteKey']
    del oxTrustConfApplicationJson['recaptchaSecretKey']

    parser.lastEntry['oxTrustConfApplication'][0] = json.dumps(oxTrustConfApplicationJson, indent=4, sort_keys=True)

    oxTrustConfCacheRefresh = parser.lastEntry['oxTrustConfCacheRefresh'][0]
    oxTrustConfCacheRefreshJson = json.loads(oxTrustConfCacheRefresh)
    oxTrustConfCacheRefreshJson['inumConfig']['bindDN'] = oxTrustConfCacheRefreshJson['inumConfig']['bindDN'].replace(
        'cn=directory manager', 'cn=directory manager,o=site')
    oxTrustConfCacheRefreshJson['snapshotFolder'] = '/var/ox/identity/cr-snapshots/'
    parser.lastEntry['oxTrustConfCacheRefresh'][0] = json.dumps(oxTrustConfCacheRefreshJson, indent=4, sort_keys=True)

    oxTrustConfImportPerson = [""]
    oxTrustConfImportPerson[0] = json.dumps(json.loads('{	"mappings": [{		"ldapName": "uid",		"displayName": "Username",		"dataType": "string",		"required": "true"	},	{		"ldapName": "givenName",		"displayName": "First Name",		"dataType": "string",		"required": "true"	},	{		"ldapName": "sn",		"displayName": "Last Name",		"dataType": "string",		"required": "true"	},	{		"ldapName": "mail",		"displayName": "Email",		"dataType": "string",		"required": "true"	},	{		"ldapName": "userPassword",		"displayName": "Password",		"dataType": "string",		"required": "false"	}]}'))
    parser.lastEntry['oxTrustConfImportPerson'] = oxTrustConfImportPerson[0]

    base64Types = ["oxTrustConfApplication", "oxTrustConfImportPerson", "oxTrustConfCacheRefresh","oxTrustConfImportPerson"]

    out = CreateLDIF(parser.lastDN, parser.getLastEntry(), base64_attrs=base64Types)
    newfile = oxTrustPath.replace('/oxtrust_config.ldif', '/oxtrust_config_new.ldif')
    # print (newfile)
    f = open(newfile, 'w')
    f.write(out)
    f.close()

    os.remove(oxTrustPath)
    os.rename(newfile, oxTrustPath)



def dooxAuthChangesFor31(self, oxAuthPath):
    parser = MyLDIF(open(oxAuthPath, 'rb'), sys.stdout)
    parser.targetAttr = "oxAuthConfDynamic"
    atr = parser.parse()
    oxAuthConfDynamic = parser.lastEntry['oxAuthConfDynamic'][0]
    oxAuthConfDynamic = oxAuthConfDynamic.replace('seam/resource/', '')
    oxAuthConfDynamic = oxAuthConfDynamic.replace('restv1/oxauth/', 'restv1/')
    oxAuthConfDynamic = oxAuthConfDynamic.replace('restv1/uma-configuration', 'restv1/uma2-configuration')
    dataOxAuthConfDynamic = json.loads(oxAuthConfDynamic)
    dataOxAuthConfDynamic['grantTypesSupported'].append('password')
    dataOxAuthConfDynamic['grantTypesSupported'].append('client_credentials')
    dataOxAuthConfDynamic['grantTypesSupported'].append('refresh_token')
    dataOxAuthConfDynamic['grantTypesSupported'].append('urn:ietf:params:oauth:grant-type:uma-ticket')
    dataOxAuthConfDynamic['accessTokenLifetime'] = 300
    dataOxAuthConfDynamic['sessionIdLifetime'] = 86400
    dataOxAuthConfDynamic['enableClientGrantTypeUpdate'] = True
    dataOxAuthConfDynamic['externalLoggerConfiguration'] = ""
    dataOxAuthConfDynamic['httpLoggingEnabled'] = False
    dataOxAuthConfDynamic['httpLoggingExludePaths'] = []
    dataOxAuthConfDynamic['logClientIdOnClientAuthentication'] = True
    dataOxAuthConfDynamic['logClientNameOnClientAuthentication'] = False
    dataOxAuthConfDynamic['persistIdTokenInLdap'] = False
    dataOxAuthConfDynamic['persistRefreshTokenInLdap'] = True
    dataOxAuthConfDynamic['personCustomObjectClassList'] = ["gluuCustomPerson", "gluuPerson"]
    dataOxAuthConfDynamic['idTokenSigningAlgValuesSupported'].append("ES512")
    dataOxAuthConfDynamic['idTokenSigningAlgValuesSupported'].append("none")

    del dataOxAuthConfDynamic['sessionStateHttpOnly']
    del dataOxAuthConfDynamic['shortLivedAccessTokenLifetime']
    del dataOxAuthConfDynamic['validateTokenEndpoint']
    del dataOxAuthConfDynamic['longLivedAccessTokenLifetime']

    dataOxAuthConfDynamic['corsConfigurationFilters'] = []
    dataCross = {
        'corsAllowedHeaders': 'Origin,Authorization,Accept,X-Requested-With,Content-Type,Access-Control-Request-Method,Access-Control-Request-Headers',
        'corsAllowedMethods': 'GET,POST,HEAD,OPTIONS', 'corsAllowedOrigins': '*', 'corsExposedHeaders': '',
        'corsLoggingEnabled': False, 'corsPreflightMaxAge': 1800, 'corsRequestDecorate': True,
        'corsSupportCredentials': True, 'filterName': 'CorsFilter'}
    dataOxAuthConfDynamic['corsConfigurationFilters'].append(dataCross)

    DynamicGrantTypeDefault = '["authorization_code","implicit","client_credentials","refresh_token","urn:ietf:params:oauth:grant-type:uma-ticket"]'
    dataOxAuthConfDynamic['dynamicGrantTypeDefault'] = (json.loads(DynamicGrantTypeDefault))

    dataOxAuthConfDynamic['responseTypesSupported'] = []
    dataOxAuthConfDynamic['responseTypesSupported'].append(json.loads('["code"]'))
    dataOxAuthConfDynamic['responseTypesSupported'].append(json.loads('["code","id_token"]'))
    dataOxAuthConfDynamic['responseTypesSupported'].append(json.loads('["token"]'))
    dataOxAuthConfDynamic['responseTypesSupported'].append(json.loads('["token","id_token"]'))
    dataOxAuthConfDynamic['responseTypesSupported'].append(json.loads('["code","token","id_token"]'))
    dataOxAuthConfDynamic['responseTypesSupported'].append(json.loads('["id_token"]'))

    dataOxAuthConfDynamic['dynamicRegistrationCustomObjectClass'] = ""
    dataOxAuthConfDynamic['dynamicRegistrationCustomAttributes'] = ['oxAuthTrustedClient']

    printOxAuthConfDynamic = json.dumps(dataOxAuthConfDynamic, indent=4, sort_keys=True)
    # print (printOxAuthConfDynamic)


    parser.lastEntry['oxAuthConfDynamic'][0] = printOxAuthConfDynamic

    dataOxAuthConfErrors = json.loads(parser.lastEntry['oxAuthConfErrors'][0])
    grant = {'id': ("invalid_grant_and_session"), 'description': (
        "he provided access token and session state are invalid or were issued to another client."), 'uri': (None)}

    session = {'id': ("session_not_passed"), 'description': ("The provided session state is empty."), 'uri': (None)}

    post_logout = {'id': ("post_logout_uri_not_passed"), 'description': ("The provided post logout uri is empty."),
                   'uri': (None)}

    post_logout_uri = {'id': ("post_logout_uri_not_associated_with_client"),
                       'description': ("The provided post logout uri is not associated with client."), 'uri': (None)}

    invalid_logout_uri = {'id': ("invalid_logout_uri"), 'description': ("The provided logout_uri is invalid."),
                          'uri': (None)}

    dataOxAuthConfErrors['endSession'].append(grant)
    dataOxAuthConfErrors['endSession'].append(session)
    dataOxAuthConfErrors['endSession'].append(post_logout)
    dataOxAuthConfErrors['endSession'].append(post_logout_uri)
    dataOxAuthConfErrors['endSession'].append(invalid_logout_uri)

    register = {'description': "Value of one or more claims_redirect_uris is invalid.",
                'id': "invalid_claims_redirect_uri", 'uri': None}

    dataOxAuthConfErrors['register'].append(register)

    uma = {'description': "The provided session is invalid.", 'id': "invalid_session", 'uri': None}
    dataOxAuthConfErrors['uma'].append(uma)

    uma1 = {'description': 'Forbidden by policy (policy returned false).', 'id': "forbidden_by_policy", 'uri': None}

    dataOxAuthConfErrors['uma'].append(uma1)

    uma2 = {'description': 'The provided permission request is not valid.', 'id': "invalid_permission_request",
            'uri': None}

    dataOxAuthConfErrors['uma'].append(uma2)

    uma3 = {
        'description': 'The claims-gathering script name is not provided or otherwise failed to load script with this name(s).',
        'id': "invalid_claims_gathering_script_name", 'uri': None}

    dataOxAuthConfErrors['uma'].append(uma3)

    uma4 = {'description': 'The provided ticket was not found at the AS.', 'id': "invalid_ticket", 'uri': None}

    dataOxAuthConfErrors['uma'].append(uma4)

    uma5 = {'description': 'The provided client_id is not valid.', 'id': "invalid_client_id", 'uri': None}

    dataOxAuthConfErrors['uma'].append(uma5)

    uma6 = {'description': 'The provided claims_redirect_uri is not valid.', 'id': "invalid_claims_redirect_uri",
            'uri': None}

    dataOxAuthConfErrors['uma'].append(uma6)

    uma7 = {
        'description': 'The claim token format is blank or otherwise not supported (supported format is http://openid.net/specs/openid-connect-core-1_0.html#IDToken).',
        'id': "invalid_claims_redirect_uri", 'uri': None}

    dataOxAuthConfErrors['uma'].append(uma7)

    uma8 = {
        'description': 'The claim token is not valid or unsupported. (If format is http://openid.net/specs/openid-connect-core-1_0.html#IDToken then claim token has to be ID Token).',
        'id': "invalid_claim_token", 'uri': None}

    dataOxAuthConfErrors['uma'].append(uma8)

    uma9 = {'description': 'PCT is invalid (revoked, expired or does not exist anymore on AS)', 'id': "invalid_pct",
            'uri': None}

    dataOxAuthConfErrors['uma'].append(uma9)

    uma10 = {'description': 'RPT is invalid (revoked, expired or does not exist anymore on AS)', 'id': "invalid_rpt",
             'uri': None}

    dataOxAuthConfErrors['uma'].append(uma10)

    uma11 = {
        'description': 'The provided grant_type valid does not equal to urn:ietf:params:oauth:grant-type:uma-ticket value which is required by UMA 2.',
        'id': "invalid_grant_type", 'uri': None}

    dataOxAuthConfErrors['uma'].append(uma11)

    # printOxAuthConfErrors = json.dumps(dataOxAuthConfErrors, indent=4, sort_keys=True)
    # print (printOxAuthConfErrors)

    base64Types = ["oxAuthConfStatic", "oxAuthConfWebKeys", "oxAuthConfErrors", "oxAuthConfDynamic"]

    out = CreateLDIF(parser.lastDN, parser.getLastEntry(), base64_attrs=base64Types)
    newfile = oxAuthPath.replace('/oxauth_config.ldif', '/oxauth_config_new.ldif')
    # print (newfile)
    f = open(newfile, 'w')
    f.write(out)
    f.close()

    os.remove(oxAuthPath)
    os.rename(newfile, oxAuthPath)


def removeDeprecatedScripts(self, oxScriptPath):
    parser = MyLDIF(open(oxScriptPath, 'rb'), sys.stdout)
    parser.parse()
    base64Types = ["oxScript"]
    newfile = oxScriptPath.replace('/scripts.ldif', '/scripts_new.ldif')
    f = open(newfile, 'a')
    for idx, val in enumerate(parser.entries):
        if 'displayName' in val:
            if val['displayName'][0] != 'uma_authorization_policy':
                out = CreateLDIF(parser.getDNs()[idx], parser.entries[idx], base64_attrs=base64Types)
                f.write(out)
    f.close()

    os.remove(oxScriptPath)
    os.rename(newfile, oxScriptPath)

def doApplinceChanges(oxappliancesPath):
    parser = MyLDIF(open(oxappliancesPath, 'rb'), sys.stdout)
    parser.parse()
    base64Types = []

    idpConfig = json.loads(parser.entries[0]['oxIDPAuthentication'][0])
    idpConfig['name'] = None
    idpConfig['priority'] = 1
    del idpConfig['version']
    del idpConfig['level']
    idpConfigJson = json.loads(idpConfig['config'])

    idpConfig['config'] = json.dumps(idpConfigJson, indent=4, sort_keys=True)
    parser.entries[0]['oxIDPAuthentication'][0] = json.dumps(idpConfig, indent=4, sort_keys=True)
    out = CreateLDIF(parser.lastDN, parser.getLastEntry(), base64_attrs=base64Types)
    newfile = oxappliancesPath.replace('/appliance.ldif', '/appliancenew.ldif')
    # print (newfile)
    f = open(newfile, 'w')
    f.write(out)
    f.close()

    os.remove(oxappliancesPath)
    os.rename(newfile, oxappliancesPath)


def doClientsChangesForUMA2(self, clientPath):
    parser = MyLDIF(open(clientPath, 'rb'), sys.stdout)
    parser.parse()
    atr = parser.parse()
    newfile = clientPath.replace('/clients.ldif', '/clients_new.ldif')
    f = open(newfile, 'w')
    base64Types = []
    for idx, val in enumerate(parser.entries):
        if 'displayName' in val:
            if val['displayName'][0] == 'Pasport Resource Server Client':
                parser.entries[idx]["oxAuthGrantType"] = ['client_credentials']
            elif val['displayName'][0] == 'SCIM Resource Server Client':
                parser.entries[idx]["oxAuthGrantType"] = ['client_credentials']
            elif val['displayName'][0] == 'Passport Requesting Party Client':
                parser.entries[idx]["oxAuthGrantType"] = ['client_credentials']
            elif val['displayName'][0] == 'SCIM Requesting Party Client':
                parser.entries[idx]["oxAuthGrantType"] = ['client_credentials']
            out = CreateLDIF(parser.getDNs()[idx], parser.entries[idx], base64_attrs=base64Types)
            f.write(out)
    f.close()
    os.remove(clientPath)
    os.rename(newfile, clientPath)


def doUmaResourcesChangesForUma2(self, UmaPath):
    scimClient = ''
    passportClient = ''
    inumOrg = self.getOrgInum()
    with open('/install/community-edition-setup/setup.properties.last', 'r') as f:
        content = f.readlines()
        for line in content:
            if 'scim_rp_client_id' in line:
                scimClient = line.replace("scim_rp_client_id=", "")
            elif 'passport_rp_client_id' in line:
                passportClient = line.replace("passport_rp_client_id=", "")

    parser = MyLDIF(open(UmaPath, 'rb'), sys.stdout)
    parser.parse()
    atr = parser.parse()
    newfile = UmaPath.replace('/uma.ldif', '/uma_new.ldif')
    f = open(newfile, 'w')
    base64Types = []
    hostname = self.getOutput([self.hostname]).strip();
    for idx, val in enumerate(parser.entries):
        if 'displayName' in val:
            if len(val['oxId'][0]) > 1 and 'ou=resource_sets' in parser.getDNs()[idx]:
                parser.getDNs()[idx] = parser.getDNs()[idx].replace('inum=' + val['inum'][0],
                                                                    'oxId=' + val['oxId'][0]).replace('resource_sets',
                                                                                                      'resources')
            if val['oxId'][0] == 'scim_access':
                parser.entries[idx]["oxId"] = ['https://' + hostname + ' /oxauth/restv1/uma/scopes/scim_access']
            elif val['oxId'][0] == 'passport_access':
                parser.entries[idx]["oxId"] = ['https://' + hostname + ' /oxauth/restv1/uma/scopes/passport_access']
            if val['displayName'][0] == 'SCIM Resource Set':
                parser.entries[idx]["oxResource"] = ['https://' + hostname + ' /identity/restv1/scim/v1']
                parser.entries[idx]['oxAssociatedClient'] = [
                    ('inum=' + scimClient + ',ou=clients,o=' + inumOrg + ",o=gluu").replace("\n", '')]
            elif val['displayName'][0] == 'Passport Resource Set':
                parser.entries[idx]["oxResource"] = ['https://' + hostname + ' /identity/restv1/passport/config']
                parser.entries[idx]['oxAssociatedClient'] = [
                    ('inum=' + passportClient + ',ou=clients,o=' + inumOrg + ",o=gluu").replace("\n", '')]

        out = CreateLDIF(parser.getDNs()[idx], parser.entries[idx], base64_attrs=base64Types)
        f.write(out)
    f.close()
    os.remove(UmaPath)
    os.rename(newfile, UmaPath)


def doOxTrustChanges(self, oxTrustPath):
    parser = MyLDIF(open(oxTrustPath, 'rb'), sys.stdout)
    parser.targetAttr = "oxTrustConfApplication"
    atr = parser.parse()
    oxTrustConfApplication = parser.lastEntry['oxTrustConfApplication'][0]
    oxTrustConfApplication = oxTrustConfApplication.replace('seam/resource/', '')
    parser.lastEntry['oxTrustConfApplication'][0] = oxTrustConfApplication;
    base64Types = ["oxTrustConfApplication", "oxTrustConfImportPerson", "oxTrustConfCacheRefresh"]

    out = CreateLDIF(parser.lastDN, parser.getLastEntry(), base64_attrs=base64Types)
    newfile = oxTrustPath.replace('/oxtrust_config.ldif', '/oxtrust_config_new.ldif')
    # print (newfile)
    f = open(newfile, 'w')
    f.write(out)
    f.close()

    os.remove(oxTrustPath)
    os.rename(newfile, oxTrustPath)


def changePassportConfigJson(self, param):
    # Read in the file
    if os.path.exists(param):
        with open(param, 'r') as file:
            filedata = file.read()

        # Replace the target string
        filedata = filedata.replace('seam/resource/', '')

        # Write the file out again
        with open(param, 'w') as file:
            file.write(filedata)


class Exporter(object):
    def __init__(self):
        self.backupDir = 'backup_3031'
        self.foldersToBackup = ['/etc/certs',
                                '/etc/gluu/conf',
                                '/opt/shibboleth-idp/conf',
                                '/opt/shibboleth-idp/metadata',
                                '/opt/gluu/jetty/identity/custom',
                                '/opt/gluu/jetty/identity/lib',
                                '/opt/gluu/jetty/oxauth/custom',
                                '/opt/gluu/jetty/oxauth/lib',
                                ]
        self.passwordFile = tempfile.mkstemp()[1]

        self.ldapsearch = '/opt/opendj/bin/ldapsearch'
        self.slapcat = '/opt/symas/bin/slapcat'
        self.mkdir = '/bin/mkdir'
        self.cat = '/bin/cat'
        self.grep = '/bin/grep'
        self.hostname = '/bin/hostname'

        self.ldapCreds = ['-h', 'localhost', '-p', '1636', '-Z', '-X', '-D',
                          'cn=directory manager,o=gluu', '-j',
                          self.passwordFile]
        self.base_dns = ['ou=people',
                         'ou=groups',
                         'ou=attributes',
                         'ou=scopes',
                         'ou=clients',
                         'ou=scripts',
                         'ou=uma',
                         'ou=hosts',
                         'ou=u2f']
        self.propertiesFn = os.path.join(self.backupDir, 'setup.properties')

    def getOutput(self, args):
        try:
            logging.debug("Running command : %s" % " ".join(args))
            p = subprocess.Popen(args, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            output, error = p.communicate()
            if error:
                logging.error(error)
                logging.debug(output)
            return output
        except:
            logging.error("Error running command : %s" % " ".join(args))
            logging.error(traceback.format_exc())
            sys.exit(1)

    def makeFolders(self):
        folders = [self.backupDir, "%s/ldif" % self.backupDir]
        for folder in folders:
            try:
                if not os.path.exists(folder):
                    self.getOutput([self.mkdir, '-p', folder])
            except:
                logging.error("Error making folder: %s", folder)
                logging.debug(traceback.format_exc())
                sys.exit(1)

    def getOrgInum(self):
        args = [self.ldapsearch] + self.ldapCreds + ['-s', 'one', '-b',
                                                     'o=gluu', 'o=*', 'dn']
        output = self.getOutput(args)
        return output.split(",")[0].split("o=")[-1]

    def prepareLdapPW(self):
        ldap_pass = None
        # read LDAP pass from setup.properties
        with open('/install/community-edition-setup/setup.properties.last',
                  'r') as sfile:
            for line in sfile:
                if 'ldapPass=' in line:
                    ldap_pass = line.split('=')[-1]
        # write it to the tmp file
        with open(self.passwordFile, 'w') as pfile:
            pfile.write(ldap_pass)
        # perform sample search
        sample = self.getOrgInum()
        if not sample:
            # get the password from the user if it fails
            ldap_pass = getpass.getpass("Enter LDAP Passsword: ")
            with open(self.passwordFile, 'w') as pfile:
                pfile.write(ldap_pass)

    def backupFiles(self):
        logging.info('Creating backup of files')
        for folder in self.foldersToBackup:
            try:
                copy_tree(folder, self.backupDir + folder)
            except:
                logging.error("Failed to backup %s", folder)
                logging.debug(traceback.format_exc())
        copyfile('/opt/gluu/schema/openldap/custom.schema', self.backupDir + "/custom.schema")

    def getLdif(self):
        logging.info('Creating backup of LDAP data')
        orgInum = self.getOrgInum()
        # Backup the data
        for basedn in self.base_dns:
            args = [self.ldapsearch] + self.ldapCreds + [
                '-b', '%s,o=%s,o=gluu' % (basedn, orgInum), 'objectclass=*']
            output = self.getOutput(args)
            ou = basedn.split("=")[-1]
            f = open("%s/ldif/%s.ldif" % (self.backupDir, ou), 'w')
            f.write(output)
            f.close()

        removeDeprecatedScripts(self, "%s/ldif/scripts.ldif" % self.backupDir)
        doClientsChangesForUMA2(self, "%s/ldif/clients.ldif" % self.backupDir)
        doUmaResourcesChangesForUma2(self, "%s/ldif/uma.ldif" % self.backupDir)
        changePassportConfigJson(self, "%s/etc/gluu/conf/passport-config.json" % self.backupDir)

        # Backup the appliance config
        args = [self.ldapsearch] + self.ldapCreds + \
               ['-b',
                'ou=appliances,o=gluu',
                '-s',
                'one',
                'objectclass=*']
        output = self.getOutput(args)
        output = output.replace('IN_MEMORY', '"IN_MEMORY"')
        output.replace('""IN_MEMORY""',"IN_MEMORY")
        output = output.replace('DEFAULT', '"DEFAULT"')
        output.replace('""DEFAULT""',"DEFAULT")

        f = open("%s/ldif/appliance.ldif" % self.backupDir, 'w')
        f.write(output)
        f.close()

        # Backup the oxtrust config
        args = [self.ldapsearch] + self.ldapCreds + \
               ['-b',
                'ou=appliances,o=gluu',
                'objectclass=oxTrustConfiguration']
        output = self.getOutput(args)
        f = open("%s/ldif/oxtrust_config.ldif" % self.backupDir, 'w')
        f.write(output)
        f.close()
        doOxTrustChanges(self, "%s/ldif/oxtrust_config.ldif" % self.backupDir)
        doApplinceChanges("%s/ldif/appliance.ldif" % self.backupDir)
        # Backup the oxauth config
        args = [self.ldapsearch] + self.ldapCreds + \
               ['-b',
                'ou=appliances,o=gluu',
                'objectclass=oxAuthConfiguration']
        output = self.getOutput(args)
        f = open("%s/ldif/oxauth_config.ldif" % self.backupDir, 'w')

        f.write(output)
        f.close()

        dooxAuthChangesFor31(self, "%s/ldif/oxauth_config.ldif" % self.backupDir)

        # Backup the trust relationships
        args = [self.ldapsearch] + self.ldapCreds + [
            '-b', 'ou=appliances,o=gluu', 'objectclass=gluuSAMLconfig']
        output = self.getOutput(args)
        f = open("%s/ldif/trust_relationships.ldif" % self.backupDir, 'w')
        f.write(output)
        f.close()

        # Backup the org
        args = [self.ldapsearch] + self.ldapCreds + [
            '-s', 'base', '-b', 'o=%s,o=gluu' % orgInum, 'objectclass=*']
        output = self.getOutput(args)
        f = open("%s/ldif/organization.ldif" % self.backupDir, 'w')
        f.write(output)
        f.close()

        # Backup o=site
        args = [self.ldapsearch] + self.ldapCreds + [
            '-b', 'o=site', '-s', 'one', 'objectclass=*']
        output = self.getOutput(args)
        f = open("%s/ldif/site.ldif" % self.backupDir, 'w')
        f.write(output)
        f.close()

    def clean(self, s):
        return s.replace('@', '').replace('!', '').replace('.', '')

    def getProp(self, prop):
        with open('/install/community-edition-setup/setup.properties.last',
                  'r') as sf:
            for line in sf:
                if "{0}=".format(prop) in line:
                    return line.split('=')[-1].strip()

    def genProperties(self):
        logging.info('Creating setup.properties backup file')
        props = {}
        props['ldapPass'] = self.getOutput([self.cat, self.passwordFile]).strip()
        props['hostname'] = self.getOutput([self.hostname]).strip()
        props['inumAppliance'] = self.getOutput(
            [self.grep, "^inum", "%s/ldif/appliance.ldif" % self.backupDir]
        ).split("\n")[0].split(":")[-1].strip()
        props['inumApplianceFN'] = self.clean(props['inumAppliance'])
        props['inumOrg'] = self.getOrgInum()
        props['inumOrgFN'] = self.clean(props['inumOrg'])
        props['baseInum'] = props['inumOrg'][:21]
        props['encode_salt'] = self.getOutput(
            [self.cat, "%s/etc/gluu/conf/salt" % self.backupDir]
        ).split("=")[-1].strip()

        props['oxauth_client_id'] = self.getProp('oxauth_client_id')
        props['scim_rs_client_id'] = self.getProp('scim_rs_client_id')
        props['scim_rp_client_id'] = self.getProp('scim_rp_client_id')
        props['passport_rp_client_id'] = self.getProp('passport_rp_client_id')
        props['passport_rs_client_id'] = self.getProp('passport_rs_client_id')
        props['version'] = self.getProp('githubBranchName').replace(
            'version_', '')
        # As the certificates are copied to the new installation, their pass
        # are required for accessing them and validating them
        props['httpdKeyPass'] = self.getProp('httpdKeyPass')
        props['shibJksPass'] = self.getProp('shibJksPass')
        props['asimbaJksPass'] = self.getProp('asimbaJksPass')

        # Preferences for installation of optional components
        props['installSaml'] = os.path.isfile(
            '/opt/shibboleth-idp/conf/idp.properties')
        props['shibboleth_version'] = 'v3'
        props['installAsimba'] = os.path.isfile(
            '/opt/gluu/jetty/asimba/webapps/asimba.war')
        props['installOxAuthRP'] = os.path.isfile(
            '/opt/gluu/jetty/oxauth-rp/webapps/oxauth-rp.war')
        props['installPassport'] = os.path.isfile(
            '/opt/gluu/node/passport/server/app.js')

        f = open(self.propertiesFn, 'w')
        for key in props.keys():
            f.write("%s=%s\n" % (key, props[key]))
        f.close()

    def export(self):
        # Call the sequence of functions that would backup the various stuff
        print("-------------------------------------------------------------")
        print("            Gluu Server Data Export Tool For v3.1.x            ")
        print("-------------------------------------------------------------")
        print("")
        self.prepareLdapPW()
        self.makeFolders()
        self.backupFiles()
        self.getLdif()
        self.genProperties()
        print("")
        print("-------------------------------------------------------------")
        print("The data has been exported to %s" % self.backupDir)
        print("-------------------------------------------------------------")


if __name__ == "__main__":
    if len(sys.argv) != 1:
        print ("Usage: python export3031.py")
    else:
        exporter = Exporter()
        exporter.export()
